from typing import Optional
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import copy
import matplotlib.pyplot as plt # type: ignore

# imported SARIMAX from statsmodels pkg
from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore
# helper functions
from ...utils import colorful, print_static_rmse, print_dynamic_rmse
from ...models.ar_based.param_finder import find_best_pdq_or_PDQ


class BuildSarimax():
    def __init__(self, metric, seasonality=False, seasonal_period=None, p_max=12, d_max=2, q_max=12, forecast_period=2, verbose=0):
        """
        Automatically build a SARIMAX Model
        """
        self.metric = metric
        self.seasonality = seasonality
        self.seasonal_period = seasonal_period
        self.p_max = p_max
        self.d_max = d_max
        self.q_max = q_max
        self.forecast_period = forecast_period
        self.verbose = verbose
        self.model = None
       

    def fit(self, ts_df):
        """
        Build a Time Series Model using SARIMAX from statsmodels.
        """
        ############ Split the data set into train and test for Cross Validation Purposes ########
        ts_train = ts_df[:-self.forecast_period]
        ts_test = ts_df[-self.forecast_period:]
        if self.verbose == 1:
            print('Data Set split into train %s and test %s for Cross Validation Purposes'
                                % (ts_train.shape, ts_test.shape))
        ############# Now find the best pdq and PDQ parameters for the model #################
        if not self.seasonality:
            print('Building a Non Seasonal Model...')
            print('\nFinding best Non Seasonal Parameters:')
            best_p, best_d, best_q, best_bic, seasonality = find_best_pdq_or_PDQ(ts_train, self.metric,
                                    self.p_max, self.d_max, self.q_max, non_seasonal_pdq=None,
                                    seasonal_period=None, seasonality=False, verbose=self.verbose)
            print('\nBest model is: Non Seasonal SARIMAX(%d,%d,%d), %s = %0.3f' % (best_p, best_d,
                                                            best_q,self.metric, best_bic))
            #### In order to get forecasts to be in the same value ranges of the orig_endogs,
            #### you must  set the simple_differencing = False and the start_params to be the
            #### same as ARIMA.
            #### THat is the only way to ensure that the output of this model is
            #### comparable to other ARIMA models
            bestmodel = SARIMAX(ts_train, order=(best_p, best_d, best_q),
                                                enforce_stationarity=False,
                                                enforce_invertibility=False,
                                                trend='ct',
                                                start_params=[0, 0, 0, 1],
                                                simple_differencing=False)
        else:
            print(colorful.BOLD + 'Building a Seasonal Model...'+colorful.END)
            print(colorful.BOLD + '\n    Finding best Non-Seasonal pdq Parameters:' + colorful.END)
            best_p, best_d, best_q, best_bic, seasonality = find_best_pdq_or_PDQ(ts_train, self.metric,
                                                self.p_max, self.d_max, self.q_max,
                                                non_seasonal_pdq=None,
                                                seasonal_period=None,
                                                seasonality=False,verbose=self.verbose)
            print(colorful.BOLD + '\n    Finding best Seasonal PDQ Model Parameters:' + colorful.END)
            best_P, best_D, best_Q, best_bic, seasonality = find_best_pdq_or_PDQ(ts_train, self.metric,
                                                self.p_max, self.d_max, self.q_max,
                                                non_seasonal_pdq=(best_p, best_d, best_q),
                                                seasonal_period=self.seasonal_period,
                                                seasonality=True, verbose=self.verbose)
            
            
            
            if seasonality:
                print('\nBest model is a Seasonal SARIMAX(%d,%d,%d)*(%d,%d,%d,%d), %s = %0.3f' % (
                                                best_p, best_d, best_q, best_P,
                                                best_D, best_Q, self.seasonal_period, self.metric, best_bic))
                #### In order to get forecasts to be in the same value ranges of the orig_endogs,
                #### you must set the simple_differencing =False and the start_params to be
                #### the same as ARIMA.
                #### THat is the only way to ensure that the output of this model is
                #### comparable to other ARIMA models
                bestmodel = SARIMAX(ts_train, order=(best_p, best_d, best_q),
                                    seasonal_order=(best_P, best_D, best_Q, self.seasonal_period),
                                    enforce_stationarity=False,
                                    enforce_invertibility=False,
                                    simple_differencing=False, trend='ct',
                                    start_params=[0, 0, 0, 1])
            else:
                print('\nBest model is a Non Seasonal SARIMAX(%d,%d,%d)' % (
                                                    best_p, best_d, best_q))
                #### In order to get forecasts to be in the same value ranges of the orig_endogs,
                #### you must set the simple_differencing =False and the start_params to be
                #### the same as ARIMA.
                #### THat is the only way to ensure that the output of this model is
                #### comparable to other ARIMA models
                bestmodel = SARIMAX(ts_train, order=(best_p, best_d, best_q),
                                    enforce_stationarity=False,
                                    enforce_invertibility=False,
                                    trend='ct',
                                    start_params=[0, 0, 0, 1],
                                    simple_differencing=False)
        
        print(colorful.BOLD + 'Fitting best SARIMAX model for full data set'+colorful.END)
        try:
            self.model = bestmodel.fit()
            print('    Best %s metric = %0.1f' % (self.metric, eval('self.model.' + self.metric)))
        except:
            print('Error: Getting Singular Matrix. Please try using other PDQ parameters or turn off Seasonality')
            return bestmodel, None, np.inf, np.inf
        
        if self.verbose == 1:
            try:
                self.model.plot_diagnostics(figsize=(16, 12))
            except:
                print('Error: SARIMAX plot diagnostic. Continuing...')
        
        ### this is needed for static forecasts ####################
        y_truth = ts_train[:]  # Note that this is only univariate analysis
        y_forecasted = self.model.predict(dynamic=False)
        concatenated = pd.concat([y_truth, y_forecasted], axis=1, keys=['original', 'predicted'])

        ### for SARIMAX, you don't have to restore differences since it predicts like actuals.###
        if self.verbose == 1:
            print('Static Forecasts:')
            # Since you are differencing the data, some original data points will not be available
            # Hence taking from first available value.
            print_static_rmse(concatenated['original'].values[best_d:],
                              concatenated['predicted'].values[best_d:],
                              verbose=self.verbose)
        
        ########### Dynamic One Step Ahead Forecast ###########################
        ### Dynamic Forecats are a better representation of true predictive power
        ## since they only use information from the time series up to a certain point,
        ## and after that, forecasts are generated using values from previous forecasted
        ## time points.
        #################################################################################
        # Now do dynamic forecast plotting for the last X steps of the data set ######

        if self.verbose == 1:
            ax = concatenated[['original', 'predicted']][best_d:].plot(figsize=(16, 12))
            startdate = ts_df.index[-self.forecast_period-1]
            pred_dynamic = self.model.get_prediction(start=startdate, dynamic=True, full_results=True)
            pred_dynamic_ci = pred_dynamic.conf_int()
            pred_dynamic.predicted_mean.plot(label='Dynamic Forecast', ax=ax)
            try:
                ax.fill_between(pred_dynamic_ci.index, pred_dynamic_ci.iloc[:, 0],
                                pred_dynamic_ci.iloc[:, 1], color='k', alpha=.25)
                ax.fill_betweenx(ax.get_ylim(), startdate, ts_train.index[-1], alpha=.1, zorder=-1)
            except:
                pass
            ax.set_xlabel('Date')
            ax.set_ylabel('Levels')
            plt.legend()
            plt.show(block=False)
        
        # Extract the dynamic predicted and true values of our time series
        res2 = self.model.get_forecast(self.forecast_period, full_results=False)
        res2_df = res2.summary_frame()
        y_forecasted = self.predict()
        if self.verbose == 1:
            print(self.model.summary())
        print('Dynamic %d-Period Forecast:' % (self.forecast_period))
        rmse, norm_rmse = print_dynamic_rmse(ts_test, y_forecasted, ts_train)
        return self.model, res2_df, rmse, norm_rmse

    def predict(self, forecast_period: Optional[int] = None):
        """
        Return the predictions
        """
        # Extract the dynamic predicted and true values of our time series
        if forecast_period is None:
            # use the forecast period used during training
            y_forecasted = self.model.forecast(self.forecast_period)
        else:
            # use the forecast period provided by the user
            y_forecasted = self.model.forecast(forecast_period)
        return y_forecasted
        


# def predicted_diffs_restored_SARIMAX(original, predicted, periods=1):
#     """
#     THIS UTILITY IS NEEDED ONLY WHEN WE HAVE SIMPLE DIFFERENCING SET TO TRUE IN SARIMAX!
#     The number of periods is equal to the differencing order (d) in the SARIMAX mode.
#     SARIMAX predicts a "differenced” prediction only when this simple_differencing=True.
#     """
#     restored = original.loc[~predicted.isnull()]
#     predicted = predicted.loc[~predicted.isnull()]
#     restored.iloc[periods:] = predicted[periods:]
#     restored = restored.cumsum()
#     res = pd.concat([original, predicted, restored], axis=1)
#     res.columns = ['original', 'pred_as_diffs', 'predicted']
#     res[['original', 'predicted']].plot()
#     print_static_rmse(concatenated['original'], concatenated['predicted'])
#     return res[['original', 'predicted']]
