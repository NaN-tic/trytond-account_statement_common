import unittest

from proteus import Model
from trytond.i18n import gettext
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules
from trytond.tools import file_open
from trytond.transaction import Transaction


class TestCommonResources(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('account_statement_common')
        Module = Model.get('ir.module')
        connector, = Module.find([
            ('name', '=', 'account_statement_enable_banking')])
        self.assertEqual(connector.state, 'not activated')
        with Transaction().start(config.database_name, 0):
            Data = config.pool.get('ir.model.data')
            View = config.pool.get('ir.ui.view')
            Translation = config.pool.get('ir.translation')
            module = 'account_statement_common'
            for data in Data.search([
                    ('module', '=', module), ('model', '=', 'ir.ui.view')]):
                view = View(data.db_id)
                model = config.pool.get(view.model)
                definition = model.fields_view_get(view.id, view.type)
                self.assertTrue(definition['arch'])
            for language, expected in (
                    ('ca', 'El tipus de pes ha de ser únic per diari.'),
                    ('es', 'El tipo de peso debe ser único por diario.')):
                with file_open(f'{module}/locale/{language}.po') as source:
                    Translation.translation_import(
                        language, module, source.read())
                with Transaction().set_context(language=language):
                    self.assertEqual(gettext(
                        module + '.msg_journal_weight_unique'), expected)
