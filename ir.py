# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from xml.etree import ElementTree

from sql import Table

from trytond.pool import PoolMeta
from trytond.tools import file_open
from trytond.transaction import Transaction


class ModelData(metaclass=PoolMeta):
    __name__ = 'ir.model.data'

    @classmethod
    def __register__(cls, module_name):
        super().__register__(module_name)
        if module_name == 'account_statement_common':
            cls.migrate_enable_banking_data()

    @classmethod
    def migrate_enable_banking_data(cls):
        "Transfer shared records before importing the common module's XML."
        old_module = 'account_statement_enable_banking'
        new_module = 'account_statement_common'
        cursor = Transaction().connection.cursor()
        data = cls.__table__()
        view = Table('ir_ui_view')
        translation = Table('ir_translation')

        # Keep database IDs, including customized sequences, menus and views.
        # Include optional XML sections even when their modules are inactive.
        identifiers = []
        for filename in ('account.xml', 'statement.xml', 'journal.xml',
                'message.xml'):
            with file_open(f'{new_module}/{filename}') as source:
                root = ElementTree.parse(source)
            identifiers.extend(
                element.attrib['id'] for element in root.iter()
                if 'id' in element.attrib and '.' not in element.attrib['id'])

        cursor.execute(*data.select(data.model, data.db_id,
                where=(data.module == old_module)
                & data.fs_id.in_(identifiers)))
        records = cursor.fetchall()
        for model, db_id in records:
            if model == 'ir.ui.view':
                cursor.execute(*view.update([view.module], [new_module],
                        where=(view.id == db_id)
                        & (view.module == old_module)))
            translation_model = model
            if model in {'ir.action.act_window', 'ir.action.wizard',
                    'ir.action.report', 'ir.action.url'}:
                translation_model = 'ir.action'
            cursor.execute(*translation.update(
                    [translation.module], [new_module],
                    where=(translation.module == old_module)
                    & (translation.type == 'model')
                    & translation.name.like(translation_model + ',%')
                    & (translation.res_id == db_id)))
        cursor.execute(*data.update([data.module], [new_module],
                where=(data.module == old_module)
                & data.fs_id.in_(identifiers)))

        # Model/field registration preserves existing ownership, so transfer it
        # explicitly. Otherwise removing the connector could remove shared data.
        model = Table('ir_model')
        field = Table('ir_model_field')
        connector_fields = [
            'aspsp_name', 'aspsp_country', 'synchronize_journal',
            'enable_banking_session',
            'enable_banking_session_allowed_bank_accounts', 'offset_days_to',
            ]
        cursor.execute(*model.update([model.module], [new_module],
                where=(model.module == old_module)
                & ~model.name.like('enable_banking.%')))
        common_fields = ((field.module == old_module)
            & ~field.model.like('enable_banking.%')
            & ~((field.model == 'account.statement.journal')
                & field.name.in_(connector_fields)))
        cursor.execute(*field.update([field.module], [new_module],
                where=common_fields))
        connector_names = [f'account.statement.journal,{name}'
            for name in connector_fields] + ['ir.cron,method']
        cursor.execute(*translation.update(
                [translation.module], [new_module],
                where=(translation.module == old_module)
                & ~translation.name.like('enable_banking.%')
                & ~translation.name.in_(connector_names)
                & ((translation.type.in_([
                            'field', 'help', 'selection', 'wizard_button',
                            'report']))
                    | ((translation.type == 'model')
                        & (translation.res_id == -1)
                        & (translation.name != 'ir.action,name'))
                    | ((translation.type == 'view')
                        & (translation.name != 'account.statement.journal')))))
        cls._get_id_cache.clear()
