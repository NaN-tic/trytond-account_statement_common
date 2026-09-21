Account Statement Common
########################

This module provides shared statement management and reconciliation. It can be
activated without a bank synchronization connector. ``account_statement_enable_banking``
depends on this module and supplies the Enable Banking API integration.
``account_statement_bankinplay`` supplies the BankInPlay adviser integration.
The journal's ``statement_provider`` selector is extended by each connector.
Connectors must restrict both scheduled and manual downloads to their selected
provider. Imported identities remain associated with their original provider.

Connector integration
=====================

Extend ``account.statement.journal`` using ``PoolMeta``. Authentication, account
selection, HTTP requests, date policies and pagination belong to the connector.
Within one Tryton transaction:

1. Call ``journal.create_import_statement(date_from, date_to)`` to lock the journal
   and create a registered statement. Both arguments are ``datetime.date`` values.
2. Normalize each page and call
   ``journal.import_statement_transactions(statement, transactions)``. It returns
   the newly saved origins and skips references already imported into that journal
   or repeated within the page.
3. Collect the returned origins from every page and call
   ``journal.finish_import_statement(statement, origins)`` exactly once after the
   download finishes. This sets the closing balance, numbers origins and queues
   suggestions when enabled. Empty statements are validated and posted.

Normalized transactions are dictionaries with these keys:

* ``entry_reference``: stable, nonempty bank transaction identifier within the
  journal. Missing references are skipped. A connector switching providers must
  account for differences in their identifiers before importing overlapping dates.
* ``date``: ``datetime.date`` selected according to the connector's date policy.
* ``amount``: signed ``Decimal`` in the journal's currency. The connector must
  validate the source currency; debits are negative.
* ``description``: optional text.
* ``balance``: optional ``Decimal`` balance after the transaction.
* ``information``: optional dictionary of bank metadata. Use
  ``remittance_information`` for payment descriptions and ISO date strings for
  ``value_date``, ``booking_date`` and ``transaction_date``. The shared suggestion
  engine consumes these canonical keys. Legacy ``eb_*`` XML identifiers are kept
  for the metadata definitions to preserve existing records.

Connectors can extend ``account.statement.origin.on_change_with_synchronized``
to protect imported origins from editing. The default is false; Enable Banking
preserves its existing rule based on the journal's session.

Configuration
=============

The ``[account_statement_common]`` configuration section accepts ``queue_name``
and ``party_similarity_threshold``. For compatibility, absent settings fall back
to the previous ``[enable_banking]`` values, then to their existing defaults.
The Enable Banking download queue continues to use ``[enable_banking] queue_name``.

Upgrading an existing Enable Banking installation
================================================

Deploy both modules together, plus the updated ``account_mx`` and ``aeat_303``
modules when installed. Refresh the module list, mark
``account_statement_common`` for activation and mark
``account_statement_enable_banking`` and the affected installed modules for
upgrade. Apply those changes together: the dependency order loads the common
module first. For command-line upgrades, use ``--activate-dependencies``.

Before loading the common XML, the registration migration transfers ownership of
shared XML records, models, fields, views and translations from the connector.
It preserves record IDs and model/table names, including statement origins,
suggestions, weights, sequences and journal links. Sessions, credentials and
Enable Banking's scheduled synchronization method remain with the connector.
The migration is idempotent. Custom modules referencing moved XML identifiers
must replace the ``account_statement_enable_banking`` prefix with
``account_statement_common``.

The ``nantic`` module continues to depend on Enable Banking. ``account_mx`` and
``aeat_303`` extend the common module independently of the selected gateway.
