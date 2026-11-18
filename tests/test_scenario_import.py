import unittest
from datetime import date
from decimal import Decimal

from proteus import Model
from trytond.modules.account.tests.tools import create_chart
from trytond.modules.company.tests.tools import create_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules
from trytond.transaction import Transaction


class TestStatementImport(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules(
            'account_statement_common', create_company, create_chart)
        Module = Model.get('ir.module')
        connector, = Module.find([
            ('name', '=', 'account_statement_enable_banking')])
        self.assertEqual(connector.state, 'not activated')
        Journal = Model.get('account.statement.journal')
        self.assertNotIn('enable_banking_session', Journal._fields)

        Account = Model.get('account.account')
        cash, = Account.find([
            ('name', '=', 'Cash and Cash Equivalents')], limit=1)
        AccountJournal = Model.get('account.journal')
        account_journal, = AccountJournal.find([('code', '=', 'STA')], limit=1)
        Sequence = Model.get('ir.sequence')
        sequence, = Sequence.find([
            ('name', '=', 'Account Statement Origin')], limit=1)
        journal = Journal(name='Imported Bank', journal=account_journal,
            account=cash, validation='balance',
            account_statement_origin_sequence=sequence)
        journal.save()
        other_journal = Journal(name='Other Bank', journal=account_journal,
            account=cash, validation='balance', search_suggestions=False,
            account_statement_origin_sequence=sequence)
        other_journal.save()

        with Transaction().start(config.database_name, config.user,
                context=config.context,
                _lock_tables=['account_statement_journal', 'ir_sequence']):
            Journal = config.pool.get('account.statement.journal')
            Origin = config.pool.get('account.statement.origin')
            Queue = config.pool.get('ir.queue')
            journal = Journal(journal.id)
            other_journal = Journal(other_journal.id)
            today = date.today()
            statement = journal.create_import_statement(today, today)
            transaction = {
                'entry_reference': 'external-1',
                'date': today,
                'amount': Decimal('42.35'),
                'description': 'Customer payment',
                'information': {'remittance_information': 'Invoice 123'},
                }
            origins = journal.import_statement_transactions(
                statement, [transaction, transaction])
            self.assertEqual(len(origins), 1)
            journal.finish_import_statement(statement, origins)
            origin, = origins
            self.assertEqual(origin.state, 'registered')
            self.assertFalse(origin.synchronized)
            self.assertTrue(origin.number)
            self.assertEqual(origin.remittance_information, 'Invoice 123')
            self.assertEqual(statement.end_balance, Decimal('42.35'))
            tasks = [task for task in Queue.search([])
                if task.data['model'] == 'account.statement.origin']
            self.assertEqual(len(tasks), 1)

            # A repeated download does not create a second origin.
            repeated = journal.create_import_statement(today, today)
            origins = journal.import_statement_transactions(
                repeated, [transaction])
            self.assertEqual(origins, [])
            journal.finish_import_statement(repeated, origins)
            self.assertEqual(repeated.state, 'posted')
            self.assertEqual(repeated.end_balance, Decimal('42.35'))

            # References from independent bank accounts must not collide.
            other = other_journal.create_import_statement(today, today)
            origins = other_journal.import_statement_transactions(
                other, [transaction])
            other_journal.finish_import_statement(other, origins)
            self.assertEqual(len(origins), 1)
            self.assertEqual(Origin.search_count([
                ('entry_reference', '=', 'external-1')]), 2)
