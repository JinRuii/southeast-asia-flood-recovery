"""Synthetic regression and raster integration checks; no study data."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

spec = importlib.util.spec_from_file_location('ntl', Path(__file__).resolve().parents[1] / 'scripts/ntl_pipeline.py')
ntl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ntl)
SETTINGS = {'before_days': 30, 'recovery_threshold': 0.9, 'max_recovery_days': 90}

class RecoveryTests(unittest.TestCase):
    def test_zero_baseline_calendar_dates_and_first_crossing(self):
        onset = pd.Timestamp('2024-02-01')
        series = pd.Series([0., 10., 2., 8., 9.], index=pd.to_datetime(
            ['2024-01-30', '2024-01-31', '2024-02-01', '2024-02-02', '2024-02-04']))
        result = ntl.event_metrics(series, onset, SETTINGS)
        self.assertEqual(result['baseline_nonzero_mean'], 10)
        self.assertEqual(result['baseline_observations'], 1)
        self.assertEqual(result['recovery_days'], 3)
        self.assertAlmostEqual(result['light_loss_rate'], .8)

    def test_no_baseline_and_no_crossing(self):
        onset = pd.Timestamp('2024-02-01')
        series = pd.Series([0., 8.], index=pd.to_datetime(['2024-01-31', '2024-02-02']))
        self.assertEqual(ntl.event_metrics(series, onset, SETTINGS)['status'], 'no_valid_baseline')
        series.iloc[0] = 10
        result = ntl.event_metrics(series, onset, SETTINGS)
        self.assertEqual(result['status'], 'no_threshold_crossing_observed')
        self.assertTrue(np.isnan(result['recovery_days']))

    def test_onset_exclusion_and_day_90_boundary(self):
        onset = pd.Timestamp('2024-02-01')
        series = pd.Series([10., 20., 20.], index=[onset-pd.Timedelta(days=1), onset, onset+pd.Timedelta(days=91)])
        self.assertFalse(ntl.event_metrics(series, onset, SETTINGS)['recovered'])
        series.loc[onset+pd.Timedelta(days=90)] = 9
        self.assertEqual(ntl.event_metrics(series, onset, SETTINGS)['recovery_days'], 90)

    def test_repeated_events_missing_grid_and_leading_zero_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame({'grid_id': ['001']*8, 'date': [20240130,20240131,20240201,20240202,20240331,20240401,20240402,20240403],
                          'light_mean': [10,10,2,9,10,2,8,10]}).to_csv(root/'panel.csv', index=False)
            events = pd.DataFrame({'grid_id': ['001','001','missing'], 'flood_start': ['2024/02/01','2024-04-01','2024-02-01']})
            events.to_csv(root/'events.csv', index=False)
            cfg = {'paths': {key: str(root/name) for key,name in [('panel_csv','panel.csv'),('events_csv','events.csv'),
                   ('event_results_csv','results.csv'),('grid_results_csv','summary.csv')]},
                   'settings': {**SETTINGS, 'apply_matrix_filter': False, 'events_encoding': 'utf-8'}}
            ntl.recover(cfg)
            result = pd.read_csv(root/'results.csv', dtype={'grid_id': str})
            self.assertEqual(result['recovery_days'].iloc[:2].tolist(), [1,2])
            self.assertEqual(result.loc[0,'grid_id'], '001')
            self.assertEqual(result.loc[2,'status'], 'grid_missing_from_panel')
            self.assertEqual(pd.read_csv(root/'summary.csv').loc[0,'mean_recovery_days'], 1.5)
            pd.concat([events,events.iloc[:1]]).to_csv(root/'events.csv', index=False)
            with self.assertRaisesRegex(ValueError, 'Duplicate grid/onset'):
                ntl.recover(cfg)

    def test_source_filter_smooths_observed_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame({'grid_id': ['1']*3, 'date': ['2024-01-01','2024-01-02','2024-01-03'],
                          'light_mean': [0.,9.,0.]}).to_csv(root/'panel.csv', index=False)
            cfg = {'paths': {'panel_csv': str(root/'panel.csv'), 'filtered_panel_csv': str(root/'filtered.csv')}}
            ntl.filter_panel(cfg)
            np.testing.assert_allclose(pd.read_csv(root/'filtered.csv')['light_mean'], [3,3,3])

class RasterTests(unittest.TestCase):
    def test_quality_cloud_zero_exclusion_crs_and_duplicate_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'raw').mkdir()
            profile = dict(driver='GTiff', height=2,width=2,count=7,dtype='uint16',
                           crs='EPSG:4326',transform=from_origin(0,2,1,1))
            bands = np.zeros((7,2,2), dtype=np.uint16)
            bands[0] = [[0,10],[20,30]]
            bands[4] = [[0,0],[2,1]]
            bands[6] = [[0,0],[0,128]]
            with rasterio.open(root/'raw/VNP46A2_20240201.tif','w',**profile) as dst:
                dst.write(bands)
            grid = gpd.GeoDataFrame({'grid_id': ['001']}, geometry=[box(0,0,2,2)],crs='EPSG:4326')
            grid.to_crs('EPSG:3857').to_file(root/'grid.gpkg',driver='GPKG')
            cfg = {'paths': {'raw_dir': str(root/'raw'),'preprocessed_dir': str(root/'clean'),
                             'clipped_dir': str(root/'clip'),'grid_file': str(root/'grid.gpkg'),'panel_csv': str(root/'panel.csv')},
                   'settings': {'raster_glob': 'VNP46A2_*.tif','date_regex': r'VNP46A2_(\d{8})','grid_id_column': 'grid_id',
                                'bands': {'light': 1,'quality': 5,'cloud': 7},'valid_quality_values': [0,1],'cloud_upper_bound': 128}}
            ntl.preprocess(cfg)
            with rasterio.open(root/'clean/VNP46A2_20240201_clean.tif') as src:
                np.testing.assert_array_equal(src.read(1), [[0,10],[0,0]])
            ntl.clip(cfg)
            ntl.build_panel(cfg)
            result = pd.read_csv(root/'panel.csv',dtype={'grid_id': str})
            self.assertEqual(result.loc[0,'light_mean'],10)
            self.assertEqual(result.loc[0,'grid_id'],'001')
            extra = gpd.GeoDataFrame({'grid_id': ['001','002']},geometry=[box(0,0,2,2),box(5,5,6,6)],crs='EPSG:4326')
            extra.to_file(root/'grid2.gpkg',driver='GPKG')
            cfg['paths']['grid_file'] = str(root/'grid2.gpkg')
            ntl.build_panel(cfg)
            self.assertTrue(np.isnan(pd.read_csv(root/'panel.csv').loc[1,'light_mean']))
            shutil.copyfile(root/'clip/VNP46A2_20240201_clean_clip.tif',root/'clip/VNP46A2_20240201_duplicate_clip.tif')
            with self.assertRaisesRegex(ValueError,'Multiple rasters'):
                ntl.build_panel(cfg)

    def test_config_paths_are_relative_to_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config.json').write_text(json.dumps({'paths': {'raw_dir': 'raw'},'settings': SETTINGS}))
            self.assertEqual(ntl.read_config(root/'config.json')['paths']['raw_dir'], str(root/'raw'))

if __name__ == '__main__':
    unittest.main()
