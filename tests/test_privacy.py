'''Logs must not carry the account name Google Play Games puts in the window title.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest


class RedactTitleTests(unittest.TestCase):

    def test_account_name_is_hidden(self):
        from app.services.window import _redact_title
        self.assertEqual(_redact_title('Clash of Clans - SomeAccount'), 'Clash of Clans - ***')

    def test_title_without_account_is_kept(self):
        from app.services.window import _redact_title
        self.assertEqual(_redact_title('Clash of Clans'), 'Clash of Clans')


if __name__ == '__main__':
    unittest.main()
