# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from types import SimpleNamespace
from unittest.mock import patch

from trytond.modules.company.tests import create_company, set_company
from trytond.pool import Pool
from trytond.pyson import PYSONDecoder, PYSONEncoder
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.transaction import Transaction


class AccountStatementCommonTestCase(ModuleTestCase):
    'Test Account Statement Common module'
    module = 'account_statement_common'
    extras = ['analytic_account']

    @with_transaction()
    def test_create_line_analytic(self):
        pool = Pool()
        Wizard = pool.get('account.statement.origin.create_line', type='wizard')
        Start = pool.get('account.statement.origin.create_line.start')
        Origin = pool.get('account.statement.origin')
        Line = pool.get('account.statement.line')
        Account = pool.get('analytic_account.account')
        Entry = pool.get('analytic.account.entry')
        company = create_company()
        other_company = create_company(name='Other company')

        with set_company(other_company):
            Account.create([{'type': 'root', 'name': 'Other root'}])
        with set_company(company), Transaction().set_context(
                active_model='account.statement.origin',
                active_id=None, active_ids=[]):
            roots = Account.create([
                {'type': 'root', 'name': 'First root'},
                {'type': 'root', 'name': 'Second root'},
                ])

            # Opening without an active record uses the context company and
            # initializes the same analytic roots as the statement line form.
            session_id, start, _ = Wizard.create()
            result = Wizard.execute(session_id, {}, start)
            defaults = result['view']['defaults']
            self.assertEqual(defaults['company'], company.id)
            names = ['analytic_accounts', 'analytic_accounts_size']
            self.assertEqual(
                {name: defaults[name] for name in names},
                Line.default_get(names))
            self.assertEqual(defaults['analytic_accounts_size'], 2)
            self.assertEqual(
                {entry['root'] for entry in defaults['analytic_accounts']},
                {root.id for root in roots})

            # A list selection may provide active_ids without active_id.
            wizard = Wizard(session_id)
            origin = SimpleNamespace(company=company)
            with Transaction().set_context(active_ids=[42]), patch.object(
                    Origin, 'browse', return_value=[origin]) as browse:
                self.assertEqual(
                    wizard.default_start(['company']), {'company': company.id})
                browse.assert_called_once_with([42])

            # Temporary entries have no origin to trigger the editable flag.
            self.assertIsNone(Start.analytic_accounts.field)
            self.assertEqual(Line.analytic_accounts.field, 'origin')
            with Transaction().set_context(Start.analytic_accounts.context):
                entry_defaults = Entry.default_get(
                    ['root', 'account', 'editable'])
            self.assertTrue(entry_defaults['editable'])
            decoder = PYSONDecoder(entry_defaults)
            for name in ['root', 'account']:
                readonly = Entry._fields[name].states['readonly']
                self.assertFalse(
                    decoder.decode(PYSONEncoder().encode(readonly)))


del ModuleTestCase
