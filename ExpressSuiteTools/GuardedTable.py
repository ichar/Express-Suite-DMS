"""
Guarded Table class with MySQL supporting
$Id: GuardedTable.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 24/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re, sys
from types import ListType, TupleType, DictType, StringType
from zLOG import LOG, DEBUG, INFO

from ntpath import basename as nt_basename, splitext as nt_splitext
from DateTime import DateTime

import ThreadLock

from Acquisition import Implicit, aq_base, aq_get, aq_parent
from AccessControl import ClassSecurityInfo
from AccessControl.PermissionRole import rolesForPermissionOn
from zExceptions import Unauthorized
from Record import Record
from ZPublisher import Publish

from Globals import PersistentMapping
from persistent.list import PersistentList

from ZODB.POSException import ConflictError, ReadConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission, _mergedLocalRoles

from Products.ZSQLCatalog.ZSQLCatalog import ZSQLCatalog as ZCatalog
from Products.ZSQLCatalog.Catalog import Catalog

import Config
from ConflictResolution import ResolveConflict
from File import addFile
from ISAMSupporter import ISAMList
from SimpleAppItem import SimpleAppItem
from SimpleObjects import Persistent, ContentBase, ContainerBase
from PortalLogger import portal_log
from TransactionManager import interrupt_thread

from Utils import InitializeClass, parseDate, cookId, _default_charset

from logging import getLogger
logger = getLogger( 'GuardedTable' )

factory_type_information = ( 
                             { 'id'              : 'Guarded Entry'
                             , 'meta_type'       : 'Guarded Entry'
                             , 'description'     : """Guarded Table item"""
                             , 'icon'            : 'registry_icon.gif'
                             , 'product'         : ''
                             , 'factory'         : ''
                             , 'immediate_view'  : ''
                             , 'disallow_manual' : 0
                             , 'allow_discussion': 0
                             , 'actions'         : ()
                             }
                           ,
                           )

class AbstractTabularBrain( Record, Implicit ):
    """
        Abstract base brain that handles looking up attributes as
        required, and provides just enough smarts to let us get the URL, path,
        and cataloged object without having to ask the catalog directly.
    """
    def has_key( self, key ):
        return self.__record_schema__.has_key(key)

    def getPath( self ):
        """Get the physical path for this record"""
        if hasattr( self, 'data_record_path_' ):
            return self.data_record_path_
        #return self.aq_parent.getpath( self.data_record_id_ )

    def getUid( self ):
        """Get the uid for this record"""
        if hasattr( self, 'data_record_uid_' ):
            return self.data_record_uid_
        return None
        #return self.aq_parent.getuid( self.data_record_id_ )

    def getChilds( self ):
        """Get the child items count for this record"""
        if hasattr( self, 'data_record_path_' ):
            return self.data_record_childs_

    def getObject( self, REQUEST=None ):
        """Try to return the object for this record"""
        return self.aq_parent.getentry(self.data_record_id_, self.getUid())

    def getRID( self ):
        """Return the record ID for this object."""
        return self.data_record_id_

    #getPath = getRID


class TabularCatalog( Catalog ):
    """
        Modified ZCatalog with TabularBrains support
    """
    def _IsDebug( self ):
        try: return self.getPhysicalRoot().getProperty('DEBUG_GuardedTable')
        except: return 1

    def useBrains( self, brains ):
        """ 
            Sets up the Catalog to return an object (ala ZTables) that
            is created on the fly from the tuple stored in the self.data
            Btree.
        """
        class tabularbrains( AbstractTabularBrain, brains ):
            pass

        scopy = {}
        for x in self.schema.keys():
            scopy[x] = self.schema[x][0]

        l = len(self.schema.keys())

        scopy['data_record_id_'] = l
        scopy['data_record_score_'] = l+1
        scopy['data_record_normalized_score_'] = l+2
        scopy['data_record_uid_'] = l+3
        scopy['data_record_path_'] = l+4
        scopy['data_record_childs_'] = l+5

        tabularbrains.__record_schema__ = scopy

        self._v_brains = brains
        self._v_result_class = tabularbrains


class GuardedEntry( ContentBase ):
    """
        Table entry with data security machinery
    """
    _class_version = 1.0

    meta_type = 'Guarded Entry'
    _default_view = 'view'

    security = ClassSecurityInfo()

    def __init__( self, id, table ):
        ContentBase.__init__( self, id )

        self.record_id = None
        self._table = table
        self._files = {}

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not ContentBase._initstate( self, mode ):
            return 0

        if getattr(self, 'modification_history', None) is None:
            self.modification_history = PersistentList()

        if getattr(self, '_data', None) is None:
            self._data = PersistentMapping()
        elif type(self._data) == DictType:
            self._data = PersistentMapping(self._data)

        return 1

    def index_html( self, REQUEST, RESPONSE ):
        """
            Returns the entry contents
        """
        return self.table_entry_form( self, REQUEST, RESPONSE )

    security.declareProtected(CMFCorePermissions.View, 'Title')
    def Title( self ):
        return "%s / %s" % (aq_parent(self).Title(), self.getId())

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'setRecordId')
    def setRecordId( self, id ):
        """
            Sets the entry record id
        """
        self.record_id = id

    security.declareProtected(CMFCorePermissions.View, 'RecordId')
    def RecordId( self ):
        """
            Returns the record id
        """
        return self.record_id

    def Creator( self ):
        return self._data.get('Creator') or ContentBase.Creator( self )

    def __getattr__( self, name ):
        if hasattr(self, '_data') and self._data.has_key(name):
            try: AQ_DATA = self._table.aq_acquire('_v_catalog_entries')
            except: AQ_DATA = None
            if AQ_DATA:
                # Unprotected get
                return self._data.get(name)
            else:
                # Secure get
                return self.__of__(self._table).get(name)

        raise AttributeError, name

    def reindex( self, idxs=[] ):
        self.catalog_object( self, self.RecordId(), idxs )

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'set')
    def set( self, name, value ):
        """
            Sets up an entry field with the given name/value.

            Arguments:

                'name' -- entry field id string

                'value' -- entry field value

            Write operation is allowed only if the 'isSetAllowed' guard
            method returns True value. 'Unauthorized' exception will raise
            otherwise.

            In case the 'value' is a string that starts with the 'uid:'
            prefix, the rest part of the string is considered to be a
            reference to the portal object by it's uid. Therefore, link
            object to the target document will be created.
        """
        if self.isSetAllowed(name) or getattr(self._table, '_v_table_update', 0):
            column = self.getColumnById(name)
            if column is not None:
                self._data[ name ] = value
                self._data['ModificationDate'] = DateTime()
                self._p_changed = 1

                # create the link to the object
                link_prefix = 'uid:'
                if type(value) == StringType and value.startswith(link_prefix):
                    destination_uid = value[len(link_prefix):]
                    # XXX Check that the destination_uid really exists
                    links = getToolByName( self, 'portal_links', None )

                    # Remove old link
                    source_uid = self.getUid()
                    old_links = links.searchLinks( source_uid=source_uid, field_id=name )
                    if old_links:
                        ids = map(lambda x: x.id, old_links)
                        links._v_force_links_remove=1
                        links.removeLinks(ids)
                        links._v_force_links_remove=0

                    links.createLink( source_uid=source_uid, destination_uid=destination_uid, \
                        relation=0, field_id=name )

            if name in self.enumerateIndexes():
                self.reindex( idxs=[ name, ] )
            return

        if getattr(self._table, '_v_table_update', 0):
            return

        raise Unauthorized, name

    security.declareProtected(CMFCorePermissions.View, 'get')
    def get( self, name, default=None, js_encode=None ):
        """
            Returns an entry field.

            Arguments:

                'name' -- entry field id string

                'default' -- default field value

                'js_encode' -- Boolean. Indicates that entry value should be
                            reformatted according to the JavaScript string
                            formatting rules.

            Read operation is allowed only if the 'isGetAllowed' guard
            method returns True value. 'Unauthorized' exception will raise
            otherwise.

            Result:

                Entry field value.
        """
        if self.isGetAllowed(name):
            data = self._data
            if data.has_key(name):
                column = self._table.getColumnById(name)
                if js_encode and column is not None and column.Type() in ['string', 'text']:
                    new_str = data[name].replace('"', r'\"')
                    new_str = re.sub('\r*\n', r'\\n\\\n', new_str)
                    new_str = re.sub(r'\\', r'\\\\', new_str)
                    new_str = re.sub(r'</(script[^>]*)>', r'<\\057\1>', new_str, re.I)
                    return new_str
                return data[name]

            if default is not None:
                return default

            #raise KeyError, name
            return
        raise Unauthorized, name

    security.declareProtected(CMFCorePermissions.View, 'isGetAllowed')
    def isGetAllowed( self, name ):
        """
            Checks whether the user is allowed to get a particular entry field.

            Arguments:

                'name' -- entry field id string

            Result:

                Boolean.
        """
        return 1

    security.declareProtected(CMFCorePermissions.View, 'isSetAllowed')
    def isSetAllowed( self, name ):
        """
            Checks whether the user is allowed to set a particular entry field.

            Arguments:

                'name' -- entry field id string

            Result:

                Boolean.
        """
        return self.allowed()

    def updateHistory( self, action='', text='' ):
        """
            Adds a record to the entry changes history.

            Arguments:

                'action' -- action id string

                'text' -- user comment
        """
        uname = _getAuthenticatedUser(self).getUserName()
        x = { 'date'   : DateTime()
            , 'actor'  : uname
            , 'action' : action
            , 'text'   : text
            }

        self.modification_history.append( x )
        self._p_changed = 1

    security.declareProtected(CMFCorePermissions.View, 'getHistory')
    def getHistory( self ):
        """
            Returns the entry changes history.

            Result:

                List of dictionaries. Each dictionary has the following keys:

                    'date' -- log record date

                    'actor' -- user id string

                    'action' -- action id string

                    'text' -- user comment
        """
        return self.modification_history

    security.declareProtected(CMFCorePermissions.View, 'getData')
    def getData( self, columns=[] ):
        """
            Returns all read-allowed entry fields.

            Arguments:

                'columns' -- List of the column ids to be queried. Empty list
                            indicates that every column value should be
                            included into results.

            Result:

                Dictionary. Entry fields are mapped as the dictionary keys and values.
        """
        result = {}
        columns = columns or self.listColumnIds()
        for col_id in columns:
             try: result[col_id] = self.get(col_id, '')
             except Unauthorized: pass
        return result

    security.declarePrivate('notify_afterAdd')
    def notify_afterAdd( self ):
        """
            Method is invoked after the entry was created.
            XXX: _instance_onCreate should be used instead.
        """
        pass

    security.declareProtected(CMFCorePermissions.View, 'allowed')
    def allowed( self ):
        """
            Checks whether the user is able to manage this entry.
        """
        creator = self._data.get('Creator')
        membername = _getAuthenticatedUser(self).getUserName()
        if creator == membername:
            return 1

        if _checkPermission(CMFCorePermissions.ManagePortal, self):
            return 1

        return 0

    def validate( self ):
        """
            Same as 'allowed' but raises Unauthorized in case the security check failed.
            XXX: Should be deprecated soon.
        """
        if not self.allowed():
            raise Unauthorized

    def SearchableText( self ):
        return ' '.join( map( str, self.getData().values() ) )

    def allowedRolesAndUsers( self ):
        # Return a list of roles and users with View permission.
        # Used by TabularCatalog to filter out items you're not allowed to see.
        allowed = {}
        for r in rolesForPermissionOn(CMFCorePermissions.View, self):
            allowed[r] = 1
        localroles = _mergedLocalRoles(self)
        for user, roles in localroles.items():
            for role in roles:
                if allowed.has_key(role):
                    allowed['user:' + user] = 1
        if allowed.has_key('Owner'):
            del allowed['Owner']
        return list(allowed.keys())

InitializeClass( GuardedEntry )


class OrdinalCounter( Persistent, Implicit ):
    """ Ordinal entries counter """

    lock = ThreadLock.allocate_lock()

    def __init__( self, connector, keys ):
        """ Initialize class instance
        """
        Persistent.__init__( self )

        # Unique keys (mapping):
        # ----------------------
        #   <sql_prefix> -- object's prefix
        #   <sql_id>     -- object's id

        self._connector = connector
        self._keys = keys

    def setValue( self, value ):
        keys = self._keys
        self._connector.update( keys=keys, counter=value )

    def getValue( self, counter=None, lock=None ):
        keys = self._keys
        x = self._connector.get( mode='records', lock=lock, **keys )
        if not x: return None
        values = x[0]
        key = self.validate(counter)
        return values.has_key(key) and values[key] or 0

    def increaseValue( self, counter=None, step=1, registry=None ):
        self.lock.acquire()
        try:
            value = self.getValue( counter, lock=1 )
            self.setValue( value + step or 1 )
        finally:
            self.lock.release()
        return value

    def validate( self, counter, value=None ):
        if counter in ( 'counter', 'daily_counter', ):
            x = counter
        else:
            x = 'counter'
        if value is not None:
            pass # XXX
        return x


class OrdinalDailyCounter( OrdinalCounter ):

    def __init__( self, connector, keys ):
        OrdinalCounter.__init__( self, connector, keys )
        self.today = DateTime()

    def getValue( self ):
        #checks for date
        if not self.today.isCurrentDay():
            self.today = DateTime()
        return self.getValue( 'daily_counter' )

    #increaseValue for now will not check self.today.
    #the reason is we call getValue() right before calling increaseValue()

    def setValue( self, value=None ):
        keys = self._keys
        if not self.today.isCurrentDay():
            value = 1
            self.today = DateTime()
        self._connector.update( daily_counter=value, **keys )


class GuardedColumn( Persistent, Implicit ):
    """
        Table column definition
    """
    security = ClassSecurityInfo()

    _class_version = 1.0

    def __init__( self, id, title=None, typ=None, allows_input=1, mandatory=0, container=None ):
        if typ not in Config.allowed_column_types:
            if typ is not None and typ.endswith('Index'):
                pass
            else:
                raise KeyError, typ

        Persistent.__init__( self )
        self._container = container
        self.id = id
        self.title = title
        self.typ = typ
        self.allows_input = allows_input
        self.mandatory = mandatory

    security.declarePublic( 'getId' )
    def getId( self ):
        """
            Returns the column id.

            Result:

                String.
        """
        return self.id

    security.declarePublic( 'Type' )
    def Type( self ):
        """
            Returns the column type.

            Allowed column types are enumerated in the Config.allowed_column_types list.

            Result:

                String.
        """
        return self.typ

    security.declarePublic( 'Type' )
    def SQLType( self ):
        """
            Returns the column SQL type.

            Result:

                _catalog_metadata tuple.
        """
        if not self.typ or self.typ == 'string':
            x = ( 'SimpleType',  0, 1, 1,  'VARCHAR',  250, 'NULL',               'MYISAM', )
        elif self.typ == 'text':
            x = ( 'SimpleType',  0, 1, 1,  'TEXT',    4000, 'NULL',               'MYISAM', )
        elif self.typ == 'float':
            x = ( 'SimpleType',  0, 1, 1,  'FLOAT',      0, 'NULL',               'MYISAM', )
        elif self.typ == 'int':
            x = ( 'SimpleType',  0, 1, 1,  'INT',        0, 'NULL',               'MYISAM', )
        elif self.typ == 'boolean':
            x = ( 'SimpleType',  0, 1, 1,  'TINYINT',    1, 'DEFAULT 0',          'MYISAM', )
        elif self.typ == 'date':
            x = ( 'SimpleType',  0, 1, 1,  'DATETIME',   0, 'NULL',               'MYISAM', )
        elif self.typ == 'listitem':
            x = ( 'ListType',    0, 1, 1,  'VARCHAR',  100, 'NOT NULL',           'MYISAM', )
        elif self.typ == 'items':
            x = ( 'ListType',    0, 1, 1,  'VARCHAR',   50, \
                                           'CHARACTER SET latin1 NOT NULL',       'MYISAM', )
        else:
            x = None
        return x

    security.declarePublic( 'Title' )
    def Title( self ):
        """
            Returns the column title.

            Result:

                String.
        """
        title = self.title
        if not title:
           return self.id.replace('_', ' ')
        return title

    security.declarePublic( 'allowsInput' )
    def allowsInput( self ):
        """
            Indicates whether the column allows user input.

            Result:

                Boolean.
        """
        return self.allows_input

    security.declarePublic( 'isMandatory' )
    def isMandatory( self ):
        """
            Indicates whether the column is not removable.

            Result:

                Boolean.
        """
        return getattr(self, 'mandatory', None)

    security.declarePublic( 'setMandatory' )
    def setMandatory( self, status ):
        """
            Sets up the column mandatory status.

            Arguments:

                'status' -- Boolean. True value should be passed to enable the
                            column mandatory status.
        """
        self.mandatory = not not status

    security.declarePublic( 'DefaultValue' )
    def DefaultValue( self ):
        """
            Returns the default column value regarding the column type.

            Result:

                Default column value.
        """
        # XXX: Should be moved out of the method code
        defaults = { 'string': ''
                   , 'text': ''
                   , 'float': 0.0
                   , 'int': 0
                   , 'boolean': 0
                   , 'date': DateTime()
                   , 'file': ''
                   , 'listitem': ''
                   , 'items': ''
                   }
        typ = self.Type()
        if defaults.has_key(typ):
            return defaults[typ]
        return

InitializeClass( GuardedColumn )


class GuardedTable( ContainerBase, SimpleAppItem, ZCatalog ):

    _class_version = 2.0

    __implements__ = ( ZCatalog.__implements__, SimpleAppItem.__implements__, )

    isPrincipiaFolderish = 0

    security = ClassSecurityInfo()

    manage_options = ZCatalog.manage_options

    # ---------------------------------------------------------------------------------------------------------- #
    #   <metadata key>             <ext_type>    <R><M><I>  <data type>      <attributes>          <engine>      #
    # ---------------------------------------------------------------------------------------------------------- #
    _default_catalog_metadata = { \
        'allowedRolesAndUsers' : ( 'ListType',    0, 0, 1,  'CHAR',      50, 'ASCII NOT NULL',     'MYISAM', ),
        'meta_type'            : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NOT NULL',     '',       ),
        'Creator'              : ( 'SimpleType',  1, 1, 1,  'CHAR',      30, 'ASCII NULL',         '',       ),
        'ModificationDate'     : ( 'SimpleType',  1, 1, 1,  'DATETIME',   0, 'NULL',               '',       ),
        'RecordId'             : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NOT NULL',     '',       ),
        'RecordState'          : ( 'SimpleType',  1, 1, 1,  'CHAR',      20, 'ASCII NULL',         '',       ),
        'SID'                  : ( 'SimpleType',  1, 1, 1,  'VARCHAR',   30, 'NULL',               '',       ),
        'ID'                   : ( 'SimpleType',  1, 1, 1,  'VARCHAR',   20, 'NULL',               '',       ),
    }

    _explicit_indexes = ( 'allowedRolesAndUsers', )

    _properties = ContainerBase._properties + ( \
        { 'id':'nd_uid',      'type':'string',  'mode':'w',  'default':''     },
        { 'id':'sql_root',    'type':'string',  'mode':'w',  'default':'root' },
        { 'id':'sql_prefix',  'type':'string',  'mode':'w',  'default':''     },
    )

    def __init__( self, id, title='', description='' ):
        self.id = id
        self.title = title
        self.description = description
        self._catalog_metadata = self._default_catalog_metadata.copy()
        self.sql_prefix = None

        SimpleAppItem.__init__( self, id )

    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        state = ResolveConflict('GuardedTable', oldState, savedState, newState, '_objects', \
                                 update_local_roles=None, \
                                 mode=1 \
                                 )
        state['modification_date'] = newState['modification_date']
        return state

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not SimpleAppItem._initstate( self, mode ):
            return 0

        logger.info("_initstate, mode %s" % mode)

        if getattr(self, 'columns', None) is None:
            self.columns = ()

        if getattr(self, '_catalog_metadata', None) is None:
            self.setupMetadata()

        if not getattr(self, 'sql_prefix', None):
            # For old versions remove catalog instance and BTrees Length
            if getattr( self, '__len__', None ) is not None:
                try:
                    del self._catalog
                    del self.__len__
                except: pass
            else:
                self.setup()

        return 1

    def _check_unindexable_content( self, object ):
        meta_type = getattr(object, 'meta_type', None)
        if not meta_type or meta_type != GuardedEntry.meta_type:
            return 1
        return None

    def _containment_onAdd( self, item, container ):
        if getattr(self, '_catalog', None) is None or not ( self.schema() and self.indexes() ):
            self.setup( force=1 )

    def _containment_onDelete( self, item, container ):
        if getattr(self, '_connector', None) is not None:
            self._connector.remove( ID=self.getId(), prefix=self.getSqlPrefix() )
        if getattr(self, '_catalog', None) is not None:
            self._catalog.drop()

    def manage_catalog( self, REQUEST, RESPONSE ):
        """ Redirect to the parent where the management screen now lives """
        RESPONSE.redirect('./manage_catalogView')

    manage_workspace = manage_catalog
    #
    #   Setup methods ============================================================================================
    #
    def check( self ):
        logger.info('check for instance: %s' % self.getId())
        self._default_catalog_metadata = dict(self._catalog_metadata)

    def setup( self, force=None, check=None ):
        """ 
            Setup Catalog instance 
        """
        id = getattr(self, 'id', None)
        sql_prefix = getattr(self, 'sql_prefix', None)
        
        logger.info('setup new instance: %s, prefix: %s, force: %s' % ( id, sql_prefix, force ))
        #
        #   Initialize the catalog
        #
        if force:
            self.setupMetadata()

        if getattr(self, '_catalog', None) is None:
            self._catalog = TabularCatalog()
        else:
            self._catalog._initschema()

        if force or getattr(self, '_connector', None) is None:
            self.setupDefaultAttributes()
        #
        #   Check indexes
        #
        if self.getSqlPrefix() and self.getId():
            self._catalog.setup()
            res = self.setupIndexes( force=force, check=check )
        else:
            res = None

        self._p_changed = 1

        if check: return res
        del res

    def setupDefaultAttributes( self ):
        """
            Setup default catalog attributes
        """
        connector = ISAMList( 'registries', Config.default_registries, engine='INNODB', container=self )
        state = connector.get( sort='prefix' )

        if state:
            prefix = max([ x[1] for x in state]) or 0
            prefix = int(prefix) + 1
        else:
            prefix = 0

        sql_prefix = getattr(self, 'sql_prefix', None) or ('00' + str(prefix))[-2:]

        self.sql_db_name = ''
        self.sql_prefix = sql_prefix
        self.sql_root = '_Root'
        self.sql_user = ''

        sql_id = self.getId()

        if not connector.get( ID=sql_id, prefix=sql_prefix ):
            connector.add( ID=sql_id, prefix=sql_prefix, counter=0, daily_counter=0 )
        self._connector = connector

        keys = { 'ID' : sql_id, 'prefix' : sql_prefix }

        self._counter = OrdinalCounter( connector, keys )
        self._daily_counter = OrdinalDailyCounter( connector, keys )

    def setupMetadata( self ):
        """
            Setup metadata list
        """
        logger.info('setupMetadata for instance: %s' % self.getId())

        catalog_metadata = self._default_catalog_metadata.copy()

        for id in self.listColumnIds():
            if id in catalog_metadata.keys():
                continue
            x = self.getColumnById(id)
            if x is None:
                continue
            catalog_metadata[id] = x.SQLType()

        self._catalog_metadata = catalog_metadata

    def setupIndexes( self, idxs=[], check=None, reindex=None, force=None, REQUEST=None ):
        """
            Configure the catalog indexes/columns settings.

            Arguments:

                'idxs' -- Not implemented.

                'check' -- If true, indicates that only catalog configuration
                          analysis to be perfomed.

                'reindex' -- try to reindex new or updated Index.

            Result:

                Boolean. Returns the value indicating whether the catalog
                configuration is up to date.
        """
        logger.info('setupIndexes for instance: %s, force: %s, reindex: %s' % ( self.getId(), force, reindex ))

        reindexed = []
        changed = { 'new_columns':[], 'old_columns':[], 'new_indexes':[], 'old_indexes':[] }
        IsChanged = 0

        columns = self.enumerateColumns()
        indexes = self.enumerateIndexes()

        # Setup new columns
        for column in columns:
            key = column[0]
            if key not in self.schema():
                if check:
                    changed['new_columns'].append( key )
                else:
                    apply( self._catalog.addColumn, column, { 'check':check } )
                IsChanged = 1

        # Setup new indexes
        for index in indexes:
            key = index[0]
            if key not in self.indexes():
                if check:
                    changed['new_indexes'].append( key )
                else:
                    apply( self._catalog.addIndex, index, { 'check':check } )
                    reindexed.append( key )
                IsChanged = 1

        root_indexes = self.getRootIndexes()

        # Remove redundant columns
        x = map(lambda x: x[0], columns)
        for key in self.schema():
            if not ( key in x or key in root_indexes ):
                if check:
                    changed['old_columns'].append( key )
                else:
                    self._catalog.delColumn( key, check=check )
                IsChanged = 1

        # Remove redundant indexes
        x = map(lambda x: x[0], indexes)
        for key in self.indexes():
            if not ( key in x or key in root_indexes ):
                if check:
                    changed['old_indexes'].append( key )
                else:
                    self._catalog.delIndex( key, check=check )
                IsChanged = 1

        if IsChanged and not check or force:
            self._initIndexes()

        elif reindex and reindexed:
            for index in reindexed:
                try:
                    self.reindexIndex( index, REQUEST=REQUEST )
                except:
                    raise
                logger.info("setupIndexes = Index: %s reindexed" % index)

        return changed

    def _initIndexes( self ):
        for uid, entry in self.objectItems():
            if entry is None:
                continue
            self.catalog_object( entry, uid )

    def default_extensions( self, metadata=None, indexes=None, id=None ):
        # Return a sequence of schema names to be cached
        rs = []
        for key in self._catalog_metadata.keys():
            if id and key != id:
                continue
            ext_type, as_root, IsMetatype, indexable, s1, s2, s3, engine  = self._catalog_metadata[key]
            if metadata and not IsMetatype: 
                continue
            if indexes and not indexable: 
                continue
            args = [ key,
                     self.getExtensionTypeValue( ext_type ),
                     '%s%s%s' % ( s1, s2 and '('+str(s2)+')' or '', s3 and ' '+s3 or '' ),
                     None,
                     as_root and 1 or 0,
                     engine,
                     ]
            if metadata: args.append( indexable )
            rs.append( tuple(args) )
        return rs

    def enumerateColumns( self, id=None ):
        return self.default_extensions( metadata=1, id=id )

    def enumerateIndexes( self, id=None ):
        return self.default_extensions( indexes=1, id=id )

    def explicitIndexes( self ):
       # Return a sequence of explicit indexes
       return self._explicit_indexes

    def _get_index_info( self, id ):
        for x in self.enumerateIndexes():
            if x[0] == id:
                return x
        return None

    def initColumnIndex( self, id ):
        """
            Creates new searchable index
        """
        if not id: return None

        x = self.getColumnById(id).SQLType()
        if not x: return None

        self._catalog_metadata[id] = x

        column = self.enumerateColumns( id=id )[0]
        apply( self.addColumn, column )

        index = self.enumerateIndexes( id=id )[0]
        apply( self.addColumn, column )

        return 1

    def reindexIndex( self, name, REQUEST=None, pghandler=None, force=None ):
        """
            Reindex index. Overriden, because we should use correct entry 'uid'
        """
        if isinstance(name, str):
            name = (name,)

        paths = self._catalog.getPaths()
        if not paths:
            self._initIndexes()
            return

        num_paths = len(paths)

        i = 0
        if pghandler:
            pghandler.init('reindexing %s' % name, num_paths)

        for p in paths:
            i += 1
            if pghandler: pghandler.report(i)
            entry = self.resolve_path(p)
            if entry is None:
                entry = self.resolve_url(p, REQUEST)
            if entry is None:
                logger.error('reindexIndex could not resolve an entry from the path %r.' % p)
            else:
                # don't update metadata when only reindexing a single index via the UI
                uid = entry.RecordId()
                self.catalog_object( entry, uid, idxs=name, update_metadata=0, pghandler=pghandler, \
                                     force=force )

        if pghandler:
            pghandler.finish()
    #
    #   'ZCatalog' interface methods ==============================================================================
    #
    def catalog_object( self, object, uid, idxs=[], update_metadata=1, pghandler=None, force=None ):
        """ Catalog an entry """
        # Enable catalog to index entries using
        # getattr without any security checks
        self._v_catalog_entries = 1
        self._catalog.catalogObject( object, uid, None, idxs, update_metadata=update_metadata, \
                                     force=force )
        # Turn careless security policy off
        self._v_catalog_entries = 0

    def uncatalog_object( self, uid, force=None ):
        """ Uncatalog an entry """
        self._catalog.uncatalogObject( uid )
    #
    #   Catalog implementary functions ============================================================================
    #
    def searchEntries( self, with_limit=None, REQUEST=None, **query ):
        """
            Calls ZCatalog.searchResults with extra arguments that
            limit the results to what the user is allowed to see depending on current user's storage type.
        """
        return self.unrestrictedSearch( REQUEST, with_limit=with_limit, **query )

    security.declarePrivate( 'unrestrictedSearch' )
    def unrestrictedSearch( self, REQUEST=None, with_limit=None, **kw ):
        """
            Run ZSQLCatalog searching
        """
        IsDebug = self._catalog._IsDebug()
        catalog_id = self.getId()

        interrupt_thread( self )

        offset = limit = rs_type = batch_start = batch_size = 0

        try:
            if with_limit:
                if REQUEST is not None and not kw.has_key('sort_limit'):
                    batch_start = int(REQUEST.get('batch_start', 1))
                    batch_size = int(REQUEST.get('batch_size', 10))
                    limit = int(REQUEST.get('batch_length', 0)) or batch_size
                    kw['sort_offset'] = offset = batch_start - 1
                    kw['sort_limit'] = limit
                kw['rs_type'] = rs_type = 1
            if kw.has_key('allowedRolesAndUsers'):
                kw['allowedRolesAndUsers'] = uniqueValues(kw['allowedRolesAndUsers'])
            if IsDebug:
                LOG('%s.unrestrictedSearch' % catalog_id, DEBUG, "batch:%s-%s-%s-%s\nkw:%s" % ( \
                    batch_start, batch_size, offset, limit, kw ))

            x = apply( ZCatalog.searchResults, (self, REQUEST), kw )

            if IsDebug:
                LOG('%s.unrestrictedSearch' % catalog_id, DEBUG, 'x: %s' % len(x))
            if rs_type:
                if type(x) is TupleType:
                    total_objects, results = x
                else:
                    total_objects = len(x)
                    results = x
                return ( total_objects, results )
            else:
                return x

        except ReadConflictError, message:
            raise
        except:
            raise

    security.declareProtected( CMFCorePermissions.View, 'addEntry' )
    def addEntry( self, data=None, REQUEST=None ):
        """
            Adds a new entry to the table.

            Arguments:

                'data' -- Dictionary representing entry contents.

                'REQUEST' -- REQUEST object containing the form data to be
                            used as the entry contents. This argument is
                            effective only if the 'data' parameter is None.
        """
        #if not self.allowed():
        #    return

        if data is None and REQUEST is not None:
            # Get entry info from REQUEST and place it into
            # the 'data' vocabulary
            expected_columns = self.listColumnIds()
            data = self.parseEntryForm(expected_columns, REQUEST)

        self._store( data )

        message = "Entry added"
        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect(self.absolute_url(message=message))

    security.declareProtected( CMFCorePermissions.View, 'editEntry' )
    def editEntry( self, record_id, data=None, comment='', REQUEST=None, redirect=1 ):
        """
            Changes the table entry.

            Arguments:

                'record_id' -- entry id string

                'data' -- Dictionary representing entry contents.

                'common' -- user comment

                'REQUEST' -- REQUEST object containing the form data to be used as the entry contents. This argument is
                            effective only if the 'data' parameter is None.

                'redirect' -- Boolean. Indicates whether it is required to redirect the user to the primary object view
                            form after the entry contents was updated.
        """
        entry = self.getEntryById(record_id)
        entry.validate()

        if REQUEST is not None:
            # Get entry info from REQUEST and place it into
            # the 'data' vocabulary
            expected_columns = self.listColumnIds()
            data = self.parseEntryForm(expected_columns, REQUEST)

        self._edit( data, record_id )
        entry.updateHistory( text=comment )

        if redirect:
            message = "Entry updated"
            if REQUEST is not None:
                REQUEST[ 'RESPONSE' ].redirect(self.absolute_url(message=message))

    security.declareProtected( CMFCorePermissions.View, 'delEntries' )
    def delEntries( self, selected_entries=[], REQUEST=None ):
        """
            Removes particular entries from the table.

            Arguments:

                'selected_entries' -- list of entries id to be removed

            Note:

                User must be granted with the 'Modify portal content'
                permission to remove the entry.
        """
        # TODO: allow creators to delete their entries
        for id in selected_entries:
             if _checkPermission('Modify portal content', self):
                  self._remove(id)

        message = "Entry deleted"
        if REQUEST is not None:
            REQUEST[ 'RESPONSE' ].redirect(self.absolute_url(message=message))

    security.declareProtected( CMFCorePermissions.View, 'getEntryById' )
    def getEntryById( self, record_id ):
        """
            Returns an entry by it's record_id (entry_XXXX).

            Argument:

                'record_id' -- entry id

            Result:

                GuardedEntry class instance.
        """
        try: entry = self._getOb(record_id)
        except: entry = None
        return entry

    security.declarePrivate( 'parseEntryForm' )
    def parseEntryForm( self, expected_columns=None, REQUEST=None ):
        """
            Parses entry data from REQUEST.

            Arguments:

                'expected_columns' -- List of field ids that should be received
                        from the form. This argument is essentially important for the
                        processing of the boolean fields.

                'REQUEST' -- REQUEST object containing the user form data.

            Result:

                Dictionary containing the data extracted from the REQUEST form.
        """
        entry_mapping = {}

        # We need to know the columns to expect from the user input form because
        # boolean false values does not add any key into the REQUEST.form namespace.
        # Boolean values are represented as the checkbox elements.
        if expected_columns is None:
            expected_columns = self.listColumnIds()

        for column_id in expected_columns:
            column = self.getColumnById( column_id )
            if not ( column and column.allowsInput() ):
                continue

            fname = column.getId()
            ftype = column.Type()
            value = REQUEST.get( fname )

            if value is None:
                continue

            if ftype == 'date':
                value = parseDate( fname, REQUEST, None )
            elif ftype == 'boolean':
                value = not not value
            elif ftype == 'file':
                file = value.file
                uid  = value.uid
                if file:
                    value = addFile( self, file=file )
                elif uid:
                    value = "uid:%s" % uid
                else:
                    continue
            elif ftype == 'listitem':
                value = type(value) not in ( TupleType, ListType ) and [ value ] or value

            if value is None:
                # should not happen
                value = column.DefaultValue()

            entry_mapping[ fname ] = value

        return entry_mapping

    def listColumns( self ):
        """
            Returns a table columns list.

            Result:

                List of GuardedColumn class instances.
        """
        columns = self.columns
        return [ col.__of__(self) for col in columns ]

    def listColumnIds( self ):
        """
            Returns a list of table columns.

            Result:

                List of columns id strings.
        """
        columns = self.columns
        return map(lambda x: x.getId(), columns)

    def listWritableColumnIds( self ):
        """
            Returns a list of writable columns.

            Result:

                List of columns id strings.
        """
        return self.listColumnIds()

    def listReadableColumnIds( self ):
        """
            Returns a list of readable columns.

            Result:

                List of columns id strings.
        """
        return self.listColumnIds()

    def addColumn( self, id=None, title='', typ='', allows_input=1, mandatory=0, index_type=None, factory=GuardedColumn, **kw ):
        """
            Adds a new table column.

            Arguments:

                'id' -- Column id string.

                'title' -- Column title.

                'typ' -- Column type string.

                'allows_input' -- Boolean value indicating whether the field allows user input.

                'mandatory' -- Boolean value indicating whether the field is removable.

                'index_type' -- String representing the type of index to be used for the column data indexing in the
                                    catalog. TextIndex is used by default for 'string' and 'text' columns; FieldIndex is used
                                    for other column types.

                'factory' -- Class to be used for constructing the column object. GuardedColumn class is used by default.

                '**kw' -- Additional arguments will be passed to the factory constructor.
        """
        # Check if exists new column id
        if not id:
            id = str(int(DateTime()))
        i = 0
        while self.getColumnById( id ):
            i += 1
            id = id + str(i)

        columns = list(self.columns)
        columns.append( factory( id=id, title=title, typ=typ, allows_input=allows_input, mandatory=mandatory, **kw ) )
        self.columns = tuple(columns)

        self.initColumnIndex( id )
        self._p_changed = 1

        return id

    addMetaColumn = addColumn

    def delColumn( self, id, setup=None ):
        """
            Removes the column from the table.

            Arguments:

                'id' -- column id string.
        """
        column = self.getColumnById(id)
        if column is not None:
            self.columns = filter( lambda x, id=id: x.getId() != id, self.columns)
            self._p_changed = 1
            del column

        catalog_metadata = self._catalog_metadata
        if catalog_metadata.has_key(id):
            del catalog_metadata[id]
            self._catalog_metadata = catalog_metadata
            self._p_changed = 1

        if not setup:
            self._catalog.delColumn( id )

    delMetaColumn = delColumn

    def getColumnById( self, id ):
        """
            Returns the column object.

            Arguments:

                'id' -- column id string.
        """
        for column in self.columns:
            if column.getId() == id:
                return column.__of__(self)

        return None

    def _store( self, entry_data, factory=GuardedEntry, counter=None ):
        """
            Low-level entry store routine.

            Arguments:

                'entry_data' -- Dictionary containing the entry contents.

                'factory' -- Class to be used for constructing the entry object. GuardedEntry class is used by default.

           Result:

             Instantiated entry object.
        """
        if counter is not None:
            id = cookId( self, id='%s_%05d' % ( 'entry', counter ) )
        else:
            id = cookId( self, prefix='entry' )

        entry = factory( id, self )
        entry.setRecordId( id )

        if not getattr(self, '_v_table_update', 0):
            entry._data['Creator'] = _getAuthenticatedUser(self).getUserName()

        self._setObject( id, entry )
        entry = self.getEntryById( id )

        # Need to know the entry uid to create document links in 'set'.
        for key in entry_data.keys():
            entry.__of__(self).set(key, entry_data[key])

        self.catalog_object( entry, id )
        entry.notify_afterAdd()

        return entry

    def _edit( self, entry_data, index ):
        """
            Low-level entry editing routine.

            Arguments:

                'entry_data' -- Dictionary containing the entry contents.

                'index' -- entry id.
        """
        entry = self.getEntryById(index)

        for key in entry_data.keys():
             entry.set( key, entry_data[key] )

        self.catalog_object( entry, index )
        entry.notify_afterAdd()

    def _remove( self, id ):
        """
            Low-level entry deletion routine.
        """
        self.uncatalog_object( id )
        self._delObject( id )

    def getentry( self, rid, uid=None ):
        """
            Returns the object through the catalog
        """
        if uid is None:
            uids = self._catalog.getUids( rid=rid )
            uid = uids and uids[0]
        return self._getOb(uid)

    ### Override it if you wish to implement non-persistent entry class ###

    def _getOb( self, id, default=None ):
        return ContainerBase._getOb( self, id )

    def _setObject( self, id, entry ):
        ContainerBase._setObject( self, id, entry )

    def _delObject( self, id ):
        ContainerBase._delObject( self, id )

InitializeClass( GuardedTable )
