import unittest
from unittest.mock import Mock, patch

import arrow
import collect_data as collector


def weather(time, height):
    return {
        'time': time,
        'waveHeight': {'sg': height}, 'wavePeriod': {'sg': 6},
        'waveDirection': {'sg': 90}, 'windSpeed': {'sg': 2},
        'windDirection': {'sg': 30}, 'seaLevel': {'sg': 0.5},
    }


class ForecastTests(unittest.TestCase):
    def test_sort_preserves_header_and_includes_all_columns(self):
        sheet = Mock(id=7)
        sheet.get_all_values.return_value = [['Date', 'Time'], ['2026-09-23', '09:00'], ['2026-09-22', '14:00']]
        collector.sort_forecast_rows(sheet)
        sheet.spreadsheet.batch_update.assert_called_once_with({'requests': [{'moveDimension': {
            'source': {'sheetId': 7, 'dimension': 'ROWS', 'startIndex': 2, 'endIndex': 3},
            'destinationIndex': 1,
        }}]})

    def test_sort_empty_sheet_is_noop(self):
        sheet = Mock(col_count=27)
        sheet.get_all_values.return_value = [collector.SHEET_HEADERS]
        collector.sort_forecast_rows(sheet)
        sheet.spreadsheet.batch_update.assert_not_called()

    def test_sort_accepts_unpadded_time_and_is_stable(self):
        sheet = Mock(id=7)
        sheet.get_all_values.return_value = [['Date', 'Time'],
            ['2026-09-21', '9:00', 'A'], ['2026-09-21', '09:00', 'B'],
            ['2026-09-21', '14:00', 'C']]
        collector.sort_forecast_rows(sheet)
        sheet.spreadsheet.batch_update.assert_not_called()

    @patch.object(collector.requests, 'get')
    def test_two_dates_use_one_request_and_match_timestamp(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'hours': [
            weather('2027-01-01T01:00:00Z', 2),
            weather('2026-12-31T02:00:00Z', 99),
            weather('2026-12-31T01:00:00Z', 1),
        ]}
        rows = collector.get_surf_data(24, 121, 'Doublelion', [9], ['2026-12-31', '2027-01-01'])
        get.assert_called_once()
        params = get.call_args.kwargs['params']
        self.assertEqual(params['start'], arrow.get('2026-12-31T01:00:00Z').timestamp())
        self.assertEqual(params['end'], arrow.get('2027-01-01T01:00:00Z').timestamp())
        self.assertEqual([(r[0], r[1], r[2]) for r in rows], [
            ('2026-12-31', '09:00', 1), ('2027-01-01', '09:00', 2),
        ])

    @patch.object(collector.requests, 'get')
    def test_no_pending_dates_uses_no_quota(self, get):
        self.assertEqual(collector.get_surf_data(24, 121, 'Doublelion', [9, 14], []), [])
        get.assert_not_called()

    @patch.object(collector.requests, 'get')
    def test_missing_hour_is_not_replaced_by_adjacent_hour(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'hours': [weather('2027-01-01T05:00:00Z', 99)]}
        self.assertEqual(collector.get_surf_data(24, 121, 'Doublelion', [14], ['2027-01-01']), [])
        self.assertEqual(get.call_args.kwargs['params']['start'], arrow.get('2027-01-01T06:00:00Z').timestamp())

    @patch.object(collector.requests, 'get')
    def test_four_slots_in_one_request(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'hours': [
            weather(f'{day}T{hour}:00:00Z', 1)
            for day in ('2026-12-31', '2027-01-01') for hour in ('01', '06')
        ]}
        rows = collector.get_surf_data(24, 121, 'Doublelion', [9, 14], ['2026-12-31', '2027-01-01'])
        self.assertEqual([(r[0], r[1]) for r in rows], [
            ('2026-12-31', '09:00'), ('2026-12-31', '14:00'),
            ('2027-01-01', '09:00'), ('2027-01-01', '14:00'),
        ])
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['params']['end'], arrow.get('2027-01-01T06:00:00Z').timestamp())


if __name__ == '__main__':
    unittest.main()
