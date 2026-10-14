"""Offline dummy-only regressions for late transport logger redaction."""
import io
import logging
import unittest
import uuid
from unittest.mock import patch

import httpx

from app.testnet.client import Credentials, TestnetReader as Reader


class TestnetLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_child_debug_warning_and_traceback_are_filtered(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        root = logging.getLogger()
        root.addHandler(handler)
        credentials = Credentials('DUMMY_ONLY_ECC_LOG_KEY', 'DUMMY_ONLY_ECC_LOG_SECRET')
        reader = Reader(credentials, transport=httpx.MockTransport(self.no_network))
        child = logging.getLogger('httpcore.ecc_late_' + uuid.uuid4().hex)
        child.setLevel(logging.DEBUG)
        try:
            child.debug('header X-MBX-APIKEY: %s', credentials.key)
            child.warning('upstream %s', credentials.secret)
            child.warning('https://testnet.binance.vision/api/v3/account?signature=dummy-only')
            try:
                raise ValueError(credentials.secret)
            except ValueError:
                child.exception('Transport failed')
            child.warning('Safe transport diagnostic')
            self.assertEqual(output.getvalue(), 'Safe transport diagnostic\n')
            self.assertIn(reader._log_filter, handler.filters)
        finally:
            await reader.close()
            root.removeHandler(handler)
            child.setLevel(logging.NOTSET)
        self.assertNotIn(reader._log_filter, handler.filters)

    async def test_last_resort_is_filtered_without_configured_handlers(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        root = logging.getLogger()
        credentials = Credentials('DUMMY_ONLY_ECC_FALLBACK_KEY', 'DUMMY_ONLY_ECC_FALLBACK_SECRET')
        with patch.object(root, 'handlers', []), patch.object(logging, 'lastResort', handler):
            reader = Reader(credentials, transport=httpx.MockTransport(self.no_network))
            child = logging.getLogger('httpcore.ecc_fallback_' + uuid.uuid4().hex)
            try:
                child.warning('Transport header %s', credentials.key)
                child.error('Transport error %s', credentials.secret)
                child.warning('Safe fallback diagnostic')
                self.assertEqual(output.getvalue(), 'Safe fallback diagnostic\n')
            finally:
                await reader.close()
        self.assertNotIn(reader._log_filter, handler.filters)

    async def test_closing_one_reader_preserves_other_reader_handler_filter(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        root = logging.getLogger()
        root.addHandler(handler)
        first = Reader(Credentials('DUMMY_ONLY_ECC_FIRST_KEY', 'DUMMY_ONLY_ECC_FIRST_SECRET'),
                              transport=httpx.MockTransport(self.no_network))
        second = Reader(Credentials('DUMMY_ONLY_ECC_SECOND_KEY', 'DUMMY_ONLY_ECC_SECOND_SECRET'),
                               transport=httpx.MockTransport(self.no_network))
        try:
            await first.close()
            self.assertNotIn(first._log_filter, handler.filters)
            self.assertIn(second._log_filter, handler.filters)
            child = logging.getLogger('httpcore.ecc_shared_' + uuid.uuid4().hex)
            child.error('Transport error %s', second._credentials.secret)
            child.warning('Safe shared diagnostic')
            self.assertEqual(output.getvalue(), 'Safe shared diagnostic\n')
        finally:
            await second.close()
            root.removeHandler(handler)
        self.assertNotIn(second._log_filter, handler.filters)

    @staticmethod
    def no_network(request):
        raise AssertionError('Logging tests must not make HTTP requests')
