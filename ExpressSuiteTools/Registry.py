"""
Implementation of the registry mechanism for documents and other objects.
Contains RegistryColumn, RegistryEntry, Registry and some auxiliary classes and methods.

$Id: Registry.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 15/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Globals
import re, string, os.path, sys

import ThreadLock
import transaction

from string import join, strip, zfill
from types import ListType, TupleType, DictType, StringType
from whrandom import random

from AccessControl import Permissions as ZopePermissions
from Acquisition import aq_base, aq_parent, aq_get
from AccessControl import ClassSecurityInfo
from DateTime import DateTime

from ZODB.POSException import ConflictError, ReadConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _getViewFor, _getAuthenticatedUser, _checkPermission
from Products.Sequences.SequenceManager import SequenceStorage

from Config import Roles, allowed_column_types, FollowupMenu
from Exceptions import SimpleError
from GuardedTable import GuardedTable, GuardedEntry, GuardedColumn
from PortalLogger import portal_log
from SimpleObjects import Persistent, ContentBase
from TransactionManager import BeginThread, CommitThread, UpdateRequestRuntime, interrupt_thread

from Utils import InitializeClass, UnrestrictedCheckObject, getObjectByUid, getClientStorageType, \
     formatPlainText, translit_string, parseDate, joinpath, splitpath, get_param

from CustomDefinitions import CustomOutsideKeys
from CustomObjects import ObjectHasCustomCategory

from logging import getLogger
logger = getLogger( 'Registry' )

MAX_SIZE_OF_NUMBER = 5
MULTIPLE_REGISTRY_ALLOWED = 0
IMPLEMENTS_FOR = 'isDocument'
REINDEX_IDXS = ( 'registry_ids', 'SearchableText', )
timeout = 1.0

factory_type_information = ( { 'id'             : 'Registry'
                             , 'meta_type'      : 'Registry'
                             , 'title'          : 'Registry'
                             , 'description'    : """Tabular report"""
                             , 'icon'           : 'registry_icon.gif'
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addRegistry'
                             , 'permissions'    : ( CMFCorePermissions.ManagePortal, )
                             , 'immediate_view' : 'registry_options_form'
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'registry_view'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  },
                                  { 'id'            : 'edit_options'
                                  , 'name'          : 'Registry options'
                                  , 'action'        : 'registry_options_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  },
                                  { 'id'            : 'import'
                                  , 'name'          : 'Import from file'
                                  , 'action'        : 'registry_import_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  , 'category'      : 'object'
                                  },
                                  { 'id'            : 'export'
                                  , 'name'          : 'Export to MS Excel'
                                  , 'action'        : 'registry_export_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  , 'category'      : 'object'
                                  }, )
                             }
                           ,
                           )

_default_states = [ \
    { 'id' : 'green',  'title' : 'realized state',            'color' : ['#DDEEDD','#60AA60'], 'selected' : [] },
    { 'id' : 'red',    'title' : 'not realized state',        'color' : ['#FFDDDD','#AA6060'], 'selected' : [] },
    { 'id' : 'purple', 'title' : 'annuled state',             'color' : ['#FF6CB6','#A60060'], 'selected' : [] },
    { 'id' : 'brown',  'title' : 'on run state',              'color' : ['#FFD2A6','#804000'], 'selected' : [] },
    { 'id' : 'blue',   'title' : 'reviewing finalized state', 'color' : ['#D8D8FF','#004080'], 'selected' : [] },
    { 'id' : 'gray',   'title' : 'on archive state',          'color' : ['#C0C0C0','#000000'], 'selected' : [] },
    { 'id' : 'white',  'title' : 'other state',               'color' : ['#FFFFFF','#000000'], 'selected' : [] },
]

def addRegistry( self, id, title='', description='' ):
    """
        Creates the Registry object.

        Arguments:

          id -- Id of the registry.

          title -- Title of the registry.

          description -- Short description of the registry.

        Result:

          None
    """
    self._setObject( id, Registry( id, title, description ) )


class RegistryColumn( GuardedColumn ):
    """
        Registry column definition
    """
    sort_index = 0
    editable_after_reg = 0
    _onCreateExpression = None

    security = ClassSecurityInfo()

    _class_version = 1.01

    def __init__( self, id, title=None, typ=None, allows_input=1, mandatory=0, container=None,
                  editable=0, visible=1, width=100, exportable=1, nowrap=0 ):
        """
            Constructs new registry column.

            Extends GuardedColumn.__init__() - adds property 'editable after
            regisration'.

            Arguments:

                'id' -- Id of the column.

                'title' -- Columns's title.

                'typ' -- Type of the column (look at Config.allowed_column_types).

                'allows_input' -- If true, column will allows input. Otherwise it will not be available for input.

                'mandatory' -- The mandatory column is not allowed for removal.

                'container' -- Container for the registry column object (Registry).

                'editable' -- If true, this column will allows data modification by creator of the entry.

                'visible' -- If false, this column is not shown # added by ishabalin at 01.12.2003

                'width' -- width of the column, that will use in export to excel
        """
        GuardedColumn.__init__( self, id, title, typ, allows_input, mandatory, container )

        self.visible = not not visible
        self.width = int( width)
        self.editable_after_reg = not not editable
        self.exportable = not not exportable
        self.nowrap = nowrap

    def _initstate( self,mode ):
        """
            Initialize attributes
        """
        if not GuardedColumn._initstate( self, mode ):
            return 0

        if not hasattr(self, 'visible'):
            self.visible = 1

        if not hasattr(self, 'width'):
            self.setWidth( 100 )

        if not hasattr(self, 'exportable'):
            self.exportable = 1

        if not hasattr(self, 'nowrap'):
            self.nowrap = 0

        return 1

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'edit')
    def edit( self, title=None, editable=None, allows_input=None, visible=None, width=None, exportable=None, nowrap=None ):
        """
            Changes title, 'editable' property and input characteristics.

            Arguments:

                'title' -- Title of the column to be shown.

                'editable' -- Boolean value (not None). If true, records in this column will allow edit.

                'allows_input' -- Boolean value (not None). If true, column will allow data input.

                'visible' -- Boolean value. If false, this column is not shown.

                'width' -- width of the column, that will used in export to excel.

            Result:

                None
        """
        if title is not None:
            self.title = title

        if allows_input is not None:
            self.allows_input = not not allows_input

        if editable is not None:
            self.editable_after_reg = not not editable

        if visible is not None:
            self.visible = not not visible

        if width is not None:
            self.setWidth(width)

        if exportable is not None:
            self.exportable = not not exportable

        if nowrap is not None:
            self.nowrap = not not nowrap

    def __cmp__( self, other ):
        #Compare operations support.
        #Used to build sorted list of columns.
        return cmp(self.sort_index, other.sort_index)

    security.declareProtected(CMFCorePermissions.View, 'isEditableAfterReg')
    def isEditableAfterReg( self ):
        """
            Returns true if column allows edit after the entry hes been added.

            Result:

                Boolean
        """
        return self.editable_after_reg

    security.declareProtected(CMFCorePermissions.View, 'computeValue')
    def computeValue( self, entry ):
        """
            Returns current value from portal_catalog for registered object
            in the entry according self._onCreateExpression.

            Arguments:

                'entry' -- RegistryEntry object.

            Note:

                If called in some context that has no acquisition wrapper
                (e.g. __getattr__()), it will be returned empty value correspnding
                column's type. Result will be the same if there is no registered
                object.

            Result:

                Type of returned value depends on columns's type.
        """
        registry_id = entry and entry.get('ID')
        catalog = getToolByName( entry, 'portal_catalog', None )
        if catalog is None:
            return None

        res = catalog.unrestrictedSearch( registry_ids=registry_id, implements=IMPLEMENTS_FOR, sort_on='path' )
        result = None

        if res:
            try:
                result = res[0][ self._onCreateExpression ]
            except:
                pass

        if result:
            if self._onCreateExpression == 'category':
                metadata = getToolByName( entry, 'portal_metadata', None )
                if metadata is not None:
                    category = metadata.getCategoryById(result)
                    if category is not None:
                        result = category.Title()

            elif self._onCreateExpression == 'state':
                category = res and res[0][ 'category' ]
                workflow = getToolByName( entry, 'portal_workflow', None )
                if workflow is not None:
                    wf_id = workflow._getCategoryWorkflowFor( res[0].getObject(), category=category )
                    state_title = None
                try:
                     state_title = workflow.getStateTitle( wf_id, result )
                except TypeError:
                    pass
                result = state_title or result

        result = self.convertToType(result)
        return result

    security.declareProtected(CMFCorePermissions.View, 'isComputed')
    def isComputed( self ):
        """
            Returns true if no input data needed (the value is computed).

            Result:

                Boolean
        """
        return self._onCreateExpression is not None

    security.declareProtected(CMFCorePermissions.View, 'convertToType')
    def convertToType( self, data ):
        """
            Converts data to type self.Type().

            Arguments:

                'data' -- Object of any type (usually string, numeric, DateTime or None)

            Note:

                If the attempt of type cast to column's type will fail, the
                    default value for this type will be returned.
        """
        result = ''

        typ = self.Type()
        if typ == 'string':
            result = data is not None and str(data) or ''
        elif typ=='float':
            result = 0.0
            try: result = float(data)
            except ValueError, TypeError:  pass
        elif typ=='int':
            result = 0
            try: result = int(data)
            except ValueError, TypeError:  pass
        elif typ=='boolean':
            result = not not data
        elif typ=='date':
            result = None
            if data is not None:
                try: result = DateTime(data)
                except IndexError, TypeError:  pass
        elif typ=='file':
            pass
        return result

    security.declareProtected( CMFCorePermissions.View, 'getSystemFieldType' )
    def getSystemFieldType( self ):
        """
            Returns type of system field.

            Result:

                _onCreateExpression string
        """
        return self._onCreateExpression

    security.declareProtected( CMFCorePermissions.View, 'isVisible' )
    def isVisible( self ):
        """
            Returns true if column is visible (is shown in view mode), or false otherwise.

            Result:

                Boolean
       """
        return getattr( self, 'visible', None )

    security.declareProtected( CMFCorePermissions.View, 'isExportable' )
    def isExportable( self ):
        """
            Returns true if column is exportable to excel, or false otherwise.

            Result:

                Boolean
        """
        return getattr( self, 'exportable', None )

    security.declareProtected( CMFCorePermissions.View, 'isNowrap' )
    def isNowrap( self ):
        """
            Returns true if column has 'nowrap' attribute (is shown in view mode), or false otherwise.

            Result:

                Boolean
       """
        return getattr( self, 'nowrap', None ) and 1 or 0

    security.declareProtected( CMFCorePermissions.View, 'getWidth' )
    def getWidth( self ):
        """
           Returns the width of the column

           Results :

               integer width
        """
        return self.width

    security.declareProtected( CMFCorePermissions.AddPortalContent, 'setWidth' )
    def setWidth( self, width ):
        """
           Changes the width of the column

           Arguments:

               'width' -- Int width.
        """
        self.width = int(width)


InitializeClass(RegistryColumn)

class RegistryEntry( GuardedEntry ):
    """
        Registry entry definition
    """
    _class_version = 1.0

    security = ClassSecurityInfo()

    def index_html( self, REQUEST, RESPONSE ):
        """
            Returns the entry contents
        """
        return self.registry_entry_form( self, REQUEST, RESPONSE )

    security.declareProtected(CMFCorePermissions.View, 'allowed')
    def allowed( self ):
        """
            Checks whether the current user is able to manage this entry
        """
        creator = self._data.get('Creator')
        membername = _getAuthenticatedUser(self).getUserName()
        if creator == membername:
            return 1
        if _checkPermission(CMFCorePermissions.ModifyPortalContent, self._table):
            return 1
        return 0

    security.declareProtected(CMFCorePermissions.View, 'isEditAllowed')
    def isEditAllowed( self, name ):
        """
            Defines whether the current user is allowed to set an entry record

            Arguments:

                'name' -- Requested record id (same as column id).
        """
        column = self._table.getColumnById(name)
        if not column:
            return 0
        has_perm = _checkPermission(CMFCorePermissions.ModifyPortalContent, self._table)
        is_owner = self._data.get('Creator', None) == _getAuthenticatedUser(self).getUserName()
        is_editable_column = hasattr(column, 'isEditableAfterReg') and column.isEditableAfterReg()
        # if has_perm or (is_owner and is_editable_column):
        if has_perm and is_editable_column:
            return 1
        return 0

    security.declareProtected(CMFCorePermissions.View, 'isEntryDeleteAllowed')
    def isEntryDeleteAllowed( self ):
        """
            Defines whether the current user is allowed to remove an entry record with entry_id
        """
        has_perm = _checkPermission(CMFCorePermissions.ModifyPortalContent, self.aq_parent)
        is_owner = self._data.get('Creator', None) == _getAuthenticatedUser(self).getUserName()
        if has_perm or ( is_owner and self.aq_parent.isDelEntryAuthorAllowed() ):
            return 1
        return 0

    def RecordState( self ):
        """
            Returns the record state according associated documents workflow state
        """
        states = []
        entry_info = self._table.listRegisteredDocumentsForEntry( self )
        if not entry_info:
            return states
        archive, documents = entry_info
        if archive:
            return ['OnArchive']
        if not documents or type(documents) is not ListType:
            return states

        for x in documents:
            ob = x.getObject()
            if ob is None or not ob.implements('isDocument'):
                continue
            states.append( ob.getWorkflowState() )

        portal_log( self, 'RegistryEntry', 'RecordState', 'reindex', ( states, self.physical_path() ) )
        return states

    def get( self, name, default=None, js_encode=None ):
        """
            Reads record with the given name from the entry or computes
            the result if the requested column is computed.

            Arguments:

                'name' -- Column id.

                'default' -- The default value (if no result found).

                'js_encode' -- Flag indicated the need of javascript quoting.

                'quoted' -- Flag indicated the need of html quoting.

            Result:

                Found data or value given in 'default' argument or None.
        """
        if self.isGetAllowed(name):
            data = self._data
            column = self._table.getColumnById(name)
            computed = column is not None and column.isComputed()

            if data.has_key(name) or ( column is not None and column.isComputed() ):
                returned_value = data.get( name ) or column.DefaultValue()
                if column is not None:
                    if computed:
                        #when called from __getattr__ there is no acquisition wrapper available here
                        store = 0
                        try:
                            returned_value = column.computeValue( self )
                            store = 1
                        except (AttributeError, KeyError):
                            pass
                        if store and ( returned_value != data.get(name) ):
                            #Computed value may change. Store it just to let sorting work
                            self._table._edit(entry_data={ name:returned_value }, index=self.record_id)
                    if js_encode and column.Type() in ['string', 'text']:
                        new_str = returned_value.replace('"', r'\"')
                        new_str = re.sub('\r*\n', r'\\n\\\n', new_str)
                        new_str = re.sub(r'\\', r'\\\\', new_str)
                        new_str = re.sub(r'</(script[^>]*)>', r'<\\057\1>', new_str, re.I)
                        return new_str
                return returned_value

            if default is not None:
                return default

            return

        raise Unauthorized, name

    def getLinkedNumber( self ):
        """
            Returns linked document number
        """
        default = [ self.get('ID'), self.get('creation_date') ]
        category = self.aq_parent.getRegistryDefaultCategoryObject()
        if category is None:
            return default
        RN = category.getRN()
        RD = category.getRD()
        if not ( RD or RN ):
            return default
        return [ self.get( RN ), self.get( RD ) ]

InitializeClass(RegistryEntry)


class Registry( GuardedTable ):
    """
        Registry class.
        Registry establishes an interaction between Express Suite DMS and conventional docflow.
    """
    _class_version = 1.01

    meta_type = 'Registry'

    security = ClassSecurityInfo()

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'delColumn' )

    export_excel_form = Globals.DTMLFile( 'skins/registry/excel_export_form', globals() )

    lock = ThreadLock.allocate_lock()

    def __init__( self, id, title='', description='' ):
        """
            Constructs new registry instance.

            Arguments:

                'id' -- Id of the registry.

                'title' -- Title of the registry.

                'description' -- Description of the registry.

                'reg_number_title' -- Title for the 'ID' (registry number) field.
        """
        GuardedTable.__init__( self, id, title, description )
        self.setDepartment('')

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not GuardedTable._initstate( self, mode ):
            return 0

        logger.info("_initstate, mode %s" % mode)

        # upgrade entries and columns (why?)
        self._v_table_update = 0

        for id in self.objectIds():
            self._upgrade( id, RegistryEntry, container=self )

        tmp_container = {}
        for col in self.columns:
            tmp_container[ col.getId() ] = col

        self.columns = ()
        for column_id in tmp_container.keys():
            self._upgrade( column_id, RegistryColumn, container=tmp_container )
        self.columns = tmp_container.values()
        del tmp_container

        # allow sort
        si = 0
        for column in self.listColumns():
            column.sort_index = si
            si += 1

        if not hasattr(self, 'excel_font_size'):
           self.excel_font_size = 10

        if not hasattr(self, 'excel_landscape_view'):
           self.excel_landscape_view = 0

        if not hasattr(self, 'parent_registry'):
            self.parent_registry = None

        if not hasattr(self, 'reg_num_forming_rule'):
            self.reg_num_forming_rule = '\Seq'

        if not hasattr(self, '_author_can_delete_entry'):
            self._author_can_delete_entry = None

        if not hasattr(self, '_current_registry'):
            self._current_registry = 1

        if getattr(self, '_kw_list', None) is None:
            self._kw_list = {}

        if getattr(self, 'ordinal_counter', None) is not None:
            delattr(self, 'ordinal_counter')

        if getattr(self, 'ordinal_daily_counter', None) is not None:
            delattr(self, 'ordinal_daily_counter')

        if getattr(self, 'view_task_count', None) is None:
            self.view_task_count = 3

        return 1

    def _instance_onCreate( self ):
        # instance creation event callback
        self.addColumn( id='ID', title='Registration number', typ='string', editable=1 )
        self.addColumn( id='creation_date', title='Creation date', typ='date', allows_input=0, mandatory=1 )
        self.addColumn( id='receipt_date', title='Receipt date', typ='date', editable=1 )
        self.addColumn( id='Creator', title='Entry creator', allows_input=0, mandatory=1, typ='string', index_type='FieldIndex' )
        self.addColumn( id='contents', title='Brief contents', typ='text', editable=1 )
        self.addColumn( id='instructions', title='Instructions', typ='text', editable=1 )
        self.addColumn( id='forwarded_to', title='Forwarded to', typ='string', editable=1 )
        self.addColumn( id='filed_to', title='Filed to', typ='string', editable=1 )
        self.addColumn( id='SID', title='SID', typ='string', allows_input=0, editable=0 )

    def _instance_onClone( self, source, item ):
        # instance clone event callback
        pass
    #
    #   Registry options ==========================================================================================
    #
    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setDepartment' )
    def setDepartment( self, department):
        """
            Sets up the department option.
            Used for the document registry id creation
        """
        self.department = department

    security.declareProtected( CMFCorePermissions.View, 'getDepartment' )
    def getDepartment( self ):
        """ 
            Returns the department option
        """
        return self.department

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setDefaultCategory' )
    def setDefaultCategory( self, category ):
        """
            Sets up the category option
        """
        setattr(self, 'default_category', category)

    security.declareProtected( CMFCorePermissions.View, 'getDefaultCategory' )
    def getDefaultCategory( self ):
        """
            Returns the category option
        """
        return getattr(self, 'default_category', None)

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setViewTaskCount' )
    def setViewTaskCount( self, value ):
        """
            Sets up view followup tasks count
        """
        try:
            v = int(value)
        except:
            v = 3
        setattr(self, 'view_task_count', v)

    security.declareProtected( CMFCorePermissions.View, 'getViewTaskCount' )
    def getViewTaskCount( self ):
        """
            Returns view followup tasks count
        """
        return getattr(self, 'view_task_count', 0)

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setDefaultStates' )
    def setDefaultStates( self, states=None, REQUEST=None, **kw ):
        """
            Sets up the registry state options
        """
        if states is not None:
            setattr(self, 'default_states', states)
            return
        if REQUEST is None:
            return

        states = []

        for state in self.getDefaultStates():
            id = state['id']
            selected = get_param( 'rs_%s_selected' % id, REQUEST, kw, default=[] )
            if type(selected) is not ListType:
                selected = [ selected ]
            states.append ( { \
                'id'       : id,
                'title'    : state['title'],
                'color'    : state['color'],
                'selected' : selected,
            } )

        setattr(self, 'default_states', states)

    security.declareProtected( CMFCorePermissions.View, 'getDefaultStates' )
    def getDefaultStates( self ):
        """
            Returns the registry state options
        """
        return getattr(self, 'default_states', _default_states)

    security.declareProtected( CMFCorePermissions.View, 'getSelectedStates' )
    def getSelectedStates( self, id=None, check=None ):
        """
            Returns the registry only selected state options
        """
        if check and not self._catalog.indexes.has_key('RecordState'):
            return None
        res = []
        for state in self.getDefaultStates():
            if id:
                if state['id'] == id:
                    return state['selected']
            elif state['selected']:
                res.append( state )
        return res

    security.declareProtected( CMFCorePermissions.View, 'getStateColor' )
    def getStateColor( self, state ):
        """
            Returns the entry state color
        """
        states = self.getDefaultStates()
        for x in states:
            if state in x['selected']:
                return x['color']
        return states[-1]['color']

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setParentRegistry' )
    def setParentRegistry( self, parent_registry='' ):
        """
            Sets up the parent registry.

            Arguments:

                'parent_registry' -- nd_uid of the parent registry.
        """
        ob = getObjectByUid( self, parent_registry )
        if ob is not None or parent_registry == '':
            self.parent_registry = parent_registry

    security.declareProtected( CMFCorePermissions.View, 'getParentRegistry' )
    def getParentRegistry( self ):
        """
            Returns uid of the parent registry.
        """
        return self.parent_registry

    security.declareProtected( CMFCorePermissions.View, 'getLastSequenceNumber' )
    def getLastSequenceNumber( self ):
        """
            Returns last sequence number
        """
        return self._counter.getValue()

    security.declareProtected( CMFCorePermissions.View, 'getRegistryDefaultCategoryObject' )
    def getRegistryDefaultCategoryObject( self ):
        """
            Returns a category of objects to keep in the registry by default
        """
        try: 
            metadata = getToolByName( self, 'portal_metadata', None )
            category = metadata.getCategoryById( self.getDefaultCategory() )
        except:
            category = None
        return category

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'setInternalCounter')
    def setInternalCounter( self, new_counter=0 ):
        """
            Sets internal counter for registry ids value.
        """
        membername = _getAuthenticatedUser(self).getUserName()
        self._counter.setValue( value=new_counter )
        logger.info("setInternalCounter %s: new counter %s, changed by %s" % ( self.getId(), new_counter, membername ))

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setRegNumFormingRule' )
    def setRegNumFormingRule( self, reg_num_forming_rule ):
        """
            Sets registry number forming rule.
        """
        self.reg_num_forming_rule = reg_num_forming_rule

    def getFolderPostfix( self, object, inherited=1 ):
        #Get object's inherited postfix
        if not object or object is None:
            return '-'

        root_path = self.portal_url()
        parent = aq_parent( object )
        postfix = None

        while parent is not None and parent.absolute_url() != root_path:
            postfix = parent.getPostfix()
            if postfix or not inherited:
                break
            parent = aq_parent( parent )

        if not postfix:
            try:
                membership = getToolByName( self, 'portal_membership', None )
                user = membership.getAuthenticatedMember()
                parent = user.getMemberDepartment( mode='folder' )
                postfix = parent.getPostfix()
            except:
                logger.info('getFolderPostfix parent: %s, %s' % ( user.getUserName(), `parent` ))

        return postfix

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'setDelEntryAuthorAllowed')
    def setDelEntryAuthorAllowed( self, is_allowed=None ):
        """
            Sets self._author_can_delete_entry.
        """
        self._author_can_delete_entry = not not is_allowed

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'setCurrentRegistry')
    def setCurrentRegistry( self, is_current=None ):
        """
            Sets self._current_registry.
        """
        self._current_registry = not not is_current

    security.declareProtected(CMFCorePermissions.ModifyPortalContent, 'setNoGaps')
    def setNoGaps( self, no_gaps=None ):
        """
            Sets self._no_gaps.
        """
        setattr(self, '_no_gaps', no_gaps)
    #
    #   Basic functions ===========================================================================================
    #
    def getEntry( self, id, force=None ):
        """ 
            Returns entry object by given id (i.e. by registry number, ID)
        """
        query = {'ID' : id }
        total_objects, entries = self.searchSortedEntries( sort_on='SID', sort_order='reverse', **query )

        if len(entries) > 0:
            for x in entries:
                try:
                    entry = x.getObject()
                except:
                    continue
                if entry is not None and entry.get('ID') == id:
                    return entry
        if force:
            for entry in self.objectValues():
                if entry.get('ID') == id:
                    return entry
        return None

    def _getSourceObject( self, came_from=None, came_version_id=None, REQUEST=None ):
        """
            Searches the object user wants to register.
            Arguments:

                'came_from' -- nd_uid of the object.

                'came_version_id' -- If user wants to register version instead of document, here is version id.

            If both 'came_from' and 'came_version_id' are None, tries to get them form REQUEST.
        """
        source = None
        came_from = came_from or REQUEST is not None and REQUEST.get('came_from') or None
        came_version_id = came_version_id or REQUEST is not None and REQUEST.get('came_version_id') or None

        if came_from:
            source = getObjectByUid( self, came_from )
            if came_version_id:
                source = source.getVersion(came_version_id)

        return source

    def sanity_check_source( self, source, data, REQUEST ):
        message = ''
        if source is None:
            message = 'Document is not present $ $ error'
        elif not MULTIPLE_REGISTRY_ALLOWED and self.isObjectRegistered( source, any=1 ):
            message = 'Document is already registered'
        elif self.isObjectRegistered( source ):
            try:
                registry_id = data['ID'] or REQUEST.get('ID', None)
            except:
                registry_id = None
            if registry_id != self.getObjectRegistryId( source ):
                message = 'Document is already registered $ $ error'
        elif self.checkObjectRegistryByOutsideNumber( data ):
            message = 'Document with outside data is already registered $ $ error'

        #if message and REQUEST is not None:
        #    ob = source or self
        #    REQUEST['RESPONSE'].redirect(ob.absolute_url( message=message ))
        return message

    security.declareProtected(CMFCorePermissions.View, 'getObjectRegistryId')
    def getObjectRegistryId( self, object ):
        """
            Returns registry id if the object has already been registered in this registry.
        """
        reg_data = getattr(object, 'registry_data', {})
        uid = self.getUid()
        for reg_id in reg_data.keys():
            if uid in reg_data[reg_id]:
                return reg_id
        return None

    def getListById( self, id='' ):
        """
            Returns elements of 'list' field.

            Arguments:

                'id' -- id of requisite field

            Result:

                List. Value of _kw_list[id]
        """
        if id in self._kw_list.keys():
            return self._kw_list[id]
        return []

    def getFpfxFormingRuleOrder( self ):
        rule = self.reg_num_forming_rule.lower()
        n_seq = rule.find('\\seq')
        n_fpfx = rule.find('\\fpfx')
        n_cpfx = rule.find('\\cpfx')
        if ( n_fpfx == -1 and n_cpfx == -1 ) or n_seq == -1:
            order = None
        elif n_fpfx < n_seq and n_cpfx < n_seq:
            order = 1
        else:
            order = 2
        return order

    security.declareProtected( CMFCorePermissions.View, 'getRegistryFilterFromCookies' )
    def getRegistryFilterFromCookies( self, REQUEST=None, key=None ):
        """
            Get users registry filter from cookies.
        """
        if not key or REQUEST is None:
            return None

        x = REQUEST.cookies.get(key)

        try:
            results = eval( x )
        except:
            results = None

        return results

    def redirect_to_parent_registry( self, REQUEST ):
        message = "Document is not registered in parent registry"
        #store data we have got in REQUEST
        dt = {}
        for key, val in REQUEST.form.items():
            dt[key] = val
        REQUEST.set('data', dt)
        REQUEST['RESPONSE'].redirect(self.absolute_url( message=message, action='registry_error_resolution' ))
        return message
    #
    #   Column implementation =====================================================================================
    #
    security.declareProtected( CMFCorePermissions.AddPortalContent, 'addColumn' )
    def addColumn( self, id=None, title='', typ='', allows_input=1, mandatory=0, editable=0, system_field=None, \
                   index_type=None, factory=RegistryColumn ):
        """
            Creates new registry column.

            Arguments:

                'id' -- Id of the created column.

                'title' -- New columns's title.

                'typ' -- Type of the column. For now it may be one of the following: 'string', 'text', 'float', 'int', 'boolean', 'date', 'file', 'listitem', 'items'.

                'allows_input' -- If true, column will allows input. Otherwise it will not be available for input.

                'mandatory' -- The mandatory column is not allowed for removal.

                'editable' -- If true, this column will allows data modification by creator of the entry.

                'system_field' -- The system field calculates it's value by requesting portal_catalog for given property of the registered object.

                    Exclusions: 'category' and 'state'. They are calculated using portal_category or portal_workflow.

                'index_type' -- String representing the type of index to be used for the column data indexing in the
                            catalog. TextIndex is used by default for 'string' and 'text' columns; FieldIndex is used for other column types.

                'factory' -- Class to be used for constructing the column object. RegistryColumn class is used by default.
        """
        if id:
            if id in ( 'state', 'record_id', 'modification_history', 'data', ):
                raise AttributeError, 'The id "%s" is already in use.' % id
            if id.startswith('_'):
                raise AttributeError, '"%s" is an invalid name because it starts with "_".' % id
            if self.getColumnById( id ) is not None:
                return

        id = GuardedTable.addColumn( self, id, title, typ, allows_input, mandatory, index_type, \
                                     factory, editable=editable )

        if id:
            column = self.getColumnById(id)
            column.sort_index = len(self.listColumns())
            if system_field:
                column._onCreateExpression = system_field
                column.allows_input = 0
                column.editable=0
                column._p_changed = 1
        return id

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'editColumn' )
    def editColumn( self, id=None, title=None, editable_after_reg=None, allows_input=None, visible=None, nowrap=None, \
                    REQUEST=None ):
        """
            Changes column properties.

            Arguments:

                'id' -- Column id.

                'title' -- Column's new title.

                'editable_after_reg' -- If true, records in the column will allow edit.

                'allows_input' -- If true, column will allow data input.

            Result:

                None
        """
        column = self.getColumnById( id )
        if column is None:
            if REQUEST is not None:
                REQUEST['RESPONSE'].redirect(self.absolute_url( action='registry_view', \
                    message='Column with given id not found.' ))
            return

        if REQUEST.has_key( 'fName' ) and REQUEST.has_key( 'fType' ):
            new_id = REQUEST.get( 'fName' )
            new_type = REQUEST.get( 'fType' )

            if new_id != id:
                column = self.getColumnById( new_id )
                if column is None:
                    self.addColumn(id=new_id, title=title, typ=new_type)

                self.copyColumnValue(id_from=id, id_to=new_id)
                column = self.getColumnById( new_id )

            elif new_type != column.Type() and new_type in allowed_column_types:
                setattr(column, 'typ', new_type)

        column.edit(title, not not editable_after_reg,
                           not not allows_input,
                           not not visible,
                           width = REQUEST.get( 'width' ),
                           exportable = REQUEST.get( 'exportable', 0),
                           nowrap= not not nowrap, 
                           )

        if column.Type() == 'listitem':
            try:
                self._kw_list[id] = list(REQUEST.get('value_list'))
            except:
                self._kw_list[id] = []

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect(self.absolute_url( action='registry_options_form', \
                message='Column data changed.' ))

        self._p_changed = 1

    def delColumn( self, id, remove_explicit=None ):
        """
            Removes column
        """
        column = self.getColumnById(id)
        if column is not None and column.isMandatory() and not remove_explicit:
            return

        self.delMetaColumn( id )

        #allow sort
        si = 0
        for column in self.listColumns():
            column.sort_index = si
            si += 1
        return

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'moveColumn' )
    def moveColumn( self, column_id=None, direction=1, REQUEST=None ):
        """
            Moves column up or down (changes order of columns).

            Arguments:

                'column_id' -- Id of the column to move.

                'direction' -- Ditection. Value 1 means move up, -1 - move down.
        """
        direction = int(direction)
        sorted_columns = self.listColumns()
        column = self.getColumnById( column_id )

        for ckey in range( len(sorted_columns) ):
            if sorted_columns[ckey].getId() == column_id:
                if direction==1 and ckey>0:
                    #move up
                    pred_column = self.getColumnById( sorted_columns[ckey-1].getId() )
                    self_index = column.sort_index
                    column.sort_index = pred_column.sort_index
                    pred_column.sort_index = self_index
                elif direction==-1 and ckey < ( len(sorted_columns) - 1 ):
                    #move down
                    next_column = self.getColumnById( sorted_columns[ckey+1].getId() )
                    self_index = column.sort_index
                    column.sort_index = next_column.sort_index
                    next_column.sort_index = self_index
                else:
                    break

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.absolute_url( action='registry_options_form' ))

    def listColumns( self ):
        """
            Returns a registry columns list.
            Extends GuardedTable.listColumns() - adds columns sorting.
        """
        lc = GuardedTable.listColumns( self )
        lc.sort()
        return lc

    def listVisibleColumns( self ):
        """
            Returns visible columns list.
            Extends listColumns()
        """
        lc = []
        for column in self.listColumns ():
            if column.isVisible ():
                lc.append (column)
        return lc

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'copyColumnValue' )
    def copyColumnValue( self, id_from=None, id_to=None ):
        """
            Copies specified fields registry value.

            Arguments:

                'id_from' -- From Attribute id.

                'id_to' -- To Attribute id.
        """
        if id_from is None or id_to is None:
            return 5

        column_from = self.getColumnById( id_from )
        column_to = self.getColumnById( id_to )

        if column_from is None or column_to is None:
            return 4

        column_to_type = column_to.Type()

        if column_to_type in ['boolean','lines','file','userlist','list','link','']:
            return 3

        IsError = 0

        #check all outside keys in entries:
        for entry in self.objectValues():
            try:
                value_from = entry.get( id_from )
                if column_to_type in ['string','text','date']:
                    value_to = str(value_from)
                elif column_to_type in ['int']:
                    value_to = int(value_from)
                elif column_to_type in ['float']:
                    value_to = float(value_from)
                else:
                    continue
            except:
                IsError = 1
                continue

            try:
                entry.set( id_to, value_to )
                entry.reindexObject()
            except:
                IsError = 2
                break

        return IsError
    #
    #   Generator functions ======================================================================================
    #
    def parseEntryForm( self, expected_columns=None, REQUEST=None ):
        """
            Parses entry data from REQUEST.

            Extends GuardedTable.parseEntryForm() - adds computed columns
                processing.

            Arguments:

                'expected_columns' -- List of field ids that should be received
                from the form. This argument is essentially important for the
                processing of the boolean fields.
        """
        columns = self.listColumns()
        computed_columns = [ x for x in columns if x.isComputed() ]
        computed_columns_ids = [ x.getId() for x in computed_columns ]

        if expected_columns is None:
            expected_columns = [ x.getId() for x in columns if not x.isComputed() ]
        else:
            expected_columns = [ x for x in expected_columns if x not in computed_columns_ids ]

        entry_mapping = GuardedTable.parseEntryForm( self, expected_columns, REQUEST )
        for column in computed_columns:
            entry_mapping[ column.getId() ] = column.DefaultValue()
        return entry_mapping

    security.declareProtected( CMFCorePermissions.AddPortalContent, 'assign' )
    def assign( self, registry_id, came_from, came_version_id, REQUEST=None):
        """
            Assigns document to the given entry ID
        """
        ob = self._getSourceObject(came_from, came_version_id, REQUEST)
        if ob is not None:
            if REQUEST is not None:
                #check if object is already registered
                if self.isObjectRegistered( ob ):
                    message = "Document is already registered"
                    ob = ob or self
                    return REQUEST['RESPONSE'].redirect(ob.absolute_url( message=message ))
            if not hasattr(ob, 'registry_data'):
                ob.registry_data = {}

            s_reg_data = getattr(ob, 'registry_data', {})

            if registry_id in s_reg_data.keys():
                if not self.getUid() in s_reg_data[ registry_id ]:
                    s_reg_data[ registry_id ].append( self.getUid() )
            else:
                s_reg_data[ registry_id ] = [ self.getUid() ]

            ob._p_changed = 1
            ob.manage_permission( ZopePermissions.delete_objects, [ Roles.Manager ], 0 )
            ob.reindexObject( idxs=['registry_ids',] )

        if REQUEST is None:
            return

        releaseSelectedDocument( redirect=0, REQUEST=REQUEST )
        message = "Document assigned"
        self.redirect( message=message )

    security.declareProtected( CMFCorePermissions.View, 'releaseSelectedDocument' )
    def releaseSelectedDocument( self, redirect=1, REQUEST=None):
        """
            Resets the document preselected for registration.
        """
        if REQUEST is None:
            return

        if REQUEST.has_key('came_from'): REQUEST.set('came_from', None)
        if REQUEST.has_key('came_version_id'): REQUEST.set('came_version_id', None)

        if redirect:
            self.redirect()

    def _generate_registry_id( self, object ):
        """
            Generates registry id for the given object according reg. number forming rule
        """
        folder_nomencl_num = object is not None and aq_parent( object ).getNomenclativeNumber() or ''
        if 'fpfx' in self.reg_num_forming_rule.lower():
            folder_postfix = self.getFolderPostfix( object )
            if not folder_postfix:
                raise SimpleError, 'Entry ID is not generated. Folder postfix is not defined'
        else:
            folder_postfix = ''
        category_postfix = object is None and '-' or ''

        if object is not None and hasattr(object, 'listCategoryMetadata'):
            metadata = object.listCategoryMetadata()
            if metadata:
                for key, val in metadata:
                    if key == 'postfix':
                        category_postfix = val
                        break

        cmds = {'fnum': (folder_nomencl_num, "The 'nomenclative number' property in the folder not specified."),
                'fpfx': (folder_postfix, "The 'postfix' property in the folder not specified."),
                'cpfx': (category_postfix, "The 'postfix' property in the document's category not specified."),
                'rdpt': (self.getDepartment(), "The department not specified."),
               }

        now = DateTime()
        counter = None
        registry_id = ''
        pattern = self.reg_num_forming_rule
        if getattr(self, '_v_table_update', 0):
            pattern = pattern or '\Seq'
        if not pattern:
            raise SimpleError, "Registration number forming rule not specified"
        escaped = 0
        pos = 0

        while pos < len(pattern):
            if escaped:
                if pattern[pos] == '\\':
                    registry_id += '\\'
                else:
                    #dates:
                    command = pattern[pos]
                    if command in ('Y', 'y', 'm', 'd', 'H', 'M'):
                        registry_id += now.strftime( '%' + command )
                        escaped=0
                        pos += 1
                        continue

                    #commands:
                    m = re.match( r'seq(\:\d+#)?(?i)', pattern[pos:] )
                    if m:
                        width = m.group(1) and m.group(1)[1:-1] or '0'
                        counter = self._counter.increaseValue( registry=self )
                        registry_id += ("%" + ".%s" % width + "d") % counter
                        pos += m.end() - 1

                    m = re.match( r'sqd(\:\d+#)?(?i)', pattern[pos:] )
                    if m:
                        width = m.group(1) and m.group(1)[1:-1] or '0'
                        counter = self._daily_counter.increaseValue()
                        registry_id += ("%" + ".%s" % width + "d") % counter
                        pos += m.end() - 1

                    for command in cmds.keys():
                        if pos + len(command) > len(pattern):
                            continue
                        if pattern[pos:pos+len(command)].lower() == command:
                            if not cmds[command][0]:
                                message = cmds[command][1]
                                raise SimpleError, message
                            registry_id += cmds[command][0]
                            pos += len(command) - 1
                            break
                escaped = 0
            else:
                if pattern[pos] == '\\':
                    escaped = 1
                else:
                    registry_id += pattern[pos]
            pos += 1

        return ( registry_id, counter, )
    #
    #   Checks function ===========================================================================================
    #
    def registry_id_exists( self, rnum=None ):
        """
            Checks either registry id is present, if corresponding entry has been occupied.

            Arguments:

                rnum -- numeric number, the next registry counter.
        """
        if not rnum:
            return 1
        try:
            rnum = int(rnum)
        except TypeError:
            return 1
        if rnum >= 10**MAX_SIZE_OF_NUMBER:
            return 1

        query = {}
        query['SID'] = ('%s%s' % (zfill('0', MAX_SIZE_OF_NUMBER), str(rnum)))[-MAX_SIZE_OF_NUMBER:] + '%'

        total_objects, entry_brains = self.searchSortedEntries( sort_on='SID', sort_order='reverse', **query )

        return total_objects > 0 and 1 or 0

    security.declareProtected( CMFCorePermissions.View, 'IsUnderEnumeration' )
    def IsUnderEnumeration( self, entry, mode='down' ):
        """
            Checks is entry registry number under enumeration (is a gap).

            Arguments:

                'entry' -- RegistryEntry which stores record about document(s)

            Result:

                String (gap1-gap2).
        """
        if self.isNoGaps():
            return None
        registry_id = entry.get('ID')
        if registry_id is None or 'SID' not in self.listColumnIds():
            return None
        sid = self.getSIDById( registry_id )
        if not sid:
            return None

        if mode == 'up':
            sid_up = self.getNumberBySID( sid, 'up' )
            sid_down = ''
        if mode == 'down':
            sid_up = ''
            sid_down = self.getNumberBySID( sid, 'down' )

        if mode == 'up' and sid_up:
            if self.searchRegistryEntries( SID=sid_up+'%' ):
                return 0
            else:
                SID = sid_up
        elif mode == 'down' and sid_down:
            if self.searchRegistryEntries( SID=sid_down+'%' ):
                return 0
            else:
                SID = sid_down

        gap1 = gap2 = SID

        while gap2:
            if mode == 'up':
                SID = self.getNumberBySID( gap2, 'up' )
            elif mode == 'down':
                SID = self.getNumberBySID( gap2, 'down' )
            if SID == gap2 or self.searchRegistryEntries( SID=SID+'%' ):
                break
            elif SID is not None:
                gap2 = SID
            else:
                break

        if gap1 < gap2:
            return gap1+'-'+gap2
        elif gap1 > gap2:
            return gap2+'-'+gap1

        return str(gap1) #sid+':'+sid_up+':'+sid_down

    def check_dublicate_number( self, registry_id, record_id=None ):
        """
            Checks if given registry id exists.

            Arguments:

                registry_id -- registry number (ID)

                record_id -- record number, such as: 'entry_00000', may be absent.
        """
        if not registry_id:
            return None

        if not record_id:
            if 'SID' in self.listColumnIds():
                rnum = self.getNumberBySID( self.getSIDById( registry_id ) )
                fpfx, number, info = self.getSIDParts( registry_id )
            else:
                rnum = number = registry_id
                info = ''
            if self.registry_id_exists( rnum=rnum ):
                if not info:
                    return number
            else:
                return 0

        entry = self.getEntry( id=registry_id )
        if entry is not None:
            if registry_id == entry.get('ID') and ( record_id is None or entry.RecordId() != record_id ):
                return registry_id

        return 0

    def isObjectRegistered( self, object=None, any=None ):
        """
            Returns true if the object has already been registered in this registry.
        """
        if object is None:
            return None
        if any:
            return object.registry_ids() and 1 or 0
        return not not self.getObjectRegistryId( object )

    def isObjectRegistryIdValid( self, registry_id=None, object=None ):
        """
            Checks either object's registry id is valid or not
        """
        if not registry_id or object is None:
            return None
        if not object.implements('isDocument'):
            return None

        IsRegistryValid = 0
        for rnum, reg_uids in object.registry_data.items():
            if rnum == registry_id and self.getUid() in reg_uids:
                IsRegistryValid = 1
                break

        return IsRegistryValid

    security.declareProtected(CMFCorePermissions.View, 'isDelEntryAuthorAllowed')
    def isDelEntryAuthorAllowed( self ):
        """
            Returns true if entry author allowed to delete entry.
        """
        return self._author_can_delete_entry

    security.declareProtected(CMFCorePermissions.View, 'isCurrentRegistry')
    def isCurrentRegistry( self ):
        """
            Returns true if this registry is used in current period.
        """
        if not hasattr(self, '_current_registry'):
            self._current_registry = 1
        return self._current_registry

    def isNoGaps( self ):
        """
            Returns true if we should not check gaps inside this registry.
        """
        return getattr(self, '_no_gaps', None) and 1 or 0

    def checkObjectRegistryByOutsideNumber( self, data ):
        """
            Checks entry if the object has already been registered in this registry.
        """
        if data is None:
            return 0

        outside_keys = CustomOutsideKeys()

        for key in outside_keys:
            if not data.has_key(key):
                return 0

        total_keys = len(outside_keys)
        IsRegistered = 0

        #check all outside keys in entries:
        for entry in self.objectValues():
            IsRegistered = 0
            for key in outside_keys:
                value = entry.get(key)
                x = data[key]
                if value and x and type(x) is StringType:
                    value = value.strip()
                    x = x.strip()
                if value and x == value:
                    IsRegistered += 1

            if IsRegistered == total_keys:
                break

        return IsRegistered == total_keys
    #
    #   Search objects implementation =============================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'listRegisteredDocumentsForEntry' )
    def listRegisteredDocumentsForEntry( self, entry ):
        """
            Searches document(s) (brains) which are registered in the entry.

            Arguments:

                'entry' -- RegistryEntry which stores record about document(s)

            Result:

                List of mybrains.
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None

        user = membership.getAuthenticatedMember()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        archive = getClientStorageType( self )

        #if IsManager:
        #    results = self.get_remote_entry( entry ) # or self.get_documents( entry )
        if IsAdmin and archive is None:
            results = self.get_remote_entry( entry ) or self.get_documents( entry )
        else:
            results = self.get_documents( entry ) or ( not archive and self.get_remote_entry( entry ) ) or [0, None]

        return results

    def get_remote_entry( self, entry ):
        """
            Returns remote objects info registered for the given entry
        """
        if entry is None:
            return None

        registry_id = entry.get('ID')
        results = []

        entry_info = getattr( entry, 'archive_state_information', None )

        if entry_info:
            if type(entry_info) is DictType and entry_info['registry_id'] == registry_id:
                results.append( 1 )
                archive_instance = 'archive'
                if entry_info.has_key('archive_instance'):
                    x = entry_info.get('archive_instance', None)
                    if x:
                        archive_instance = x
                if entry_info.has_key('uid'):
                    entry_info['archive_locate_url'] = '/%s/portal_links/locate?uid=%s' % ( archive_instance, entry_info['uid'] )
                elif entry_info.has_key('archive_url'):
                    entry_info['archive_locate_url'] = '/%s%s' % ( archive_instance, entry_info['archive_url'] )
                else:
                    entry_info['archive_locate_url'] = None
                results.append( entry_info )

        return results

    def get_documents( self, entry ):
        """
            Returns local objects info registered for the given entry
        """
        if entry is None:
            return None

        registry_id = entry.get('ID')
        results = []

        if registry_id is None:
            return None
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        documents = catalog.searchResults( registry_ids=registry_id, implements=IMPLEMENTS_FOR, sort_on='path' )

        if documents:
            registry_data = None
            record_id = entry.RecordId()
            res = []

            try:
                #leave documents registered only in this registry
                for x in documents:
                    ob = x.getObject()
                    if ob is None:
                        continue

                    registry_data = getattr( ob, 'registry_data', None ) or {}

                    if not registry_data:
                        pass
                    elif self.getUid() in registry_data.get(registry_id, []):
                        res.append( x )

            except:
                logger.error('listRegisteredDocumentsForEntry %s %s %s' % ( self.getUid(), record_id, registry_data ))
                res = []
                #raise

            if len(res) > 0:
                results.append( 0 )
                results.append( res )

        return results

    def searchRegistryEntries( self, **query ):
        try:
            res = self.searchEntries( **query )
        except AttributeError:
            res = None
        return res

    def searchSortedEntries( self, sort_on=None, sort_order=None, selected_state=None, REQUEST=None, **query ):
        """
            Returns sorted registry entries list according the query.

            Arguments:

                selected_state -- selected record state, in accordance with getSelectedStates method.

            Results:

                Entries list (catalog mybrains list).
        """
        if REQUEST is not None:
            sort_on = REQUEST.get('sort_on')
            sort_order = REQUEST.get('sort_order')
        else:
            query['sort_on'] = sort_on
            query['sort_order'] = sort_order
            query['sort_limit'] = None

        portal_log( self, 'Registry', 'searchSortedEntries', 'query', ( query, sort_on, sort_order, selected_state ) )

        if selected_state:
            states = self.getSelectedStates( selected_state ) or None
            if states:
                query['RecordState'] = states

        total_objects, entries = GuardedTable.searchEntries( self, with_limit=1, REQUEST=REQUEST, **query )

        portal_log( self, 'Registry', 'searchSortedEntries', 'results', ( total_objects, len( entries ) ) )

        return ( total_objects, entries, )
    #
    #   Export/Import API =========================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'exportToExcel' )
    def exportToExcel( self, REQUEST=None ):
        """
            Generates html (with xml parts) presentation of the registry.

            Generated html is saved as *.xls file.

            Note:
                Partial support for Excel 97, full support for Excel 2000 and above.

            Result:
                HTML text.

        """
        lang = getToolByName( self, 'portal_membership' ).getLanguage( REQUEST=REQUEST )
        filename = self.id # self.Title() or 
        filename = re.sub( r'[^\w\.\_\-\s~]+(?L)', '', filename )

        if not filename:
            filename = 'file'

        setHeader = REQUEST.RESPONSE.setHeader
        setHeader("Content-Type", "application/vnd.ms-excel; name='excel'");
        setHeader("Content-type", "application/octet-stream");
        setHeader("Content-Disposition", "attachment; filename=%s.xls" % filename);
        setHeader("Cache-Control", "must-revalidate, post-check=0, pre-check=0");
        setHeader("Pragma", "no-cache");
        setHeader("Expires", "0");

        self.excel_font_size = font_size = REQUEST.get('font_size')
        self.excel_landscape_view = landscape_view = REQUEST.get('landscape_view',0)
        columns = [x.getId() for x in self.listColumns() if REQUEST.get(x.getId())]
        widths = [ REQUEST.get('width_%s'%x) for x in columns ]
        include_changes_log = REQUEST.get('include_changes_log')

        result_text = self.export_excel_form(self
                                            , REQUEST=REQUEST
                                            , columns_ids=columns
                                            , widths=widths
                                            , include_log=include_changes_log
                                            , excel_font_size=font_size
                                            , excel_landscape_view=landscape_view
                                            )

        interrupt_thread( self )

        return result_text

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'importFromCSV' )
    def importFromCSV( self, csv_file=None, csv_columns=None, ignore_titles=None, use_internal_reg_numbers=None, REQUEST=None ):
        """
            Imports data from CSV(comma separated values) file.

            Arguments:

                'csv_file'  -- FileUpload instance - file in MS Excel CSV format.

                'csv_columns'  -- Columns ids to be imported. Specifies order
                    of columns in the file.

                'ignore_titles' -- If true it is considered that the first row
                    in the file contains titles.

                'use_internal_reg_numbers' -- If true, registrative numbers for
                    entries will be generated according forming rule.

            Note:

                Tested only MS Excel format of CSV file.

            Result:

                None. Redirect with status message.
        """
        if not csv_file:
            message = 'Please choose file'
        if not csv_columns:
            message = 'Please choose column(s)'
        elif isinstance( csv_file, ListType):
            #this bug may take place in IE5.0, when interface language is
            # set to english, file name contains russian characters.
            message = 'Please use the same language as characters in the file name'
        else:
            data = csv_file.readlines()
            csv_file.close()
            if not data:
                message = "File is empty"
                if REQUEST is not None:
                    return self.redirect( REQUEST=REQUEST, message=message )

            #TODO: remove comments in data(#).
            raw_lines = map(strip, data)
            lines = []
            line = ''
            #long line may be splitted by '\\'
            for l in raw_lines:
                if not l:
                    continue
                if l.endswith('\\'):
                    line += l[:-1] + '\n'
                else:
                    lines.append(line + l)
                    line = ''

            if ignore_titles:
                lines = lines[1:]

            message = None
            for line in lines:
                flds = list(self._line_process(line, separator=';'))
                data = {}

                if use_internal_reg_numbers:
                    try:
                        csv_columns.remove('ID')
                    except ValueError:
                        pass
                columns = [self.getColumnById(x) for x in csv_columns]

                #columns = filter( lambda x: x.allowsInput(), self.listColumns())
                if len(flds) != len(columns):
                    raise IndexError, 'Number of columns in the file does not match.'

                #convert all fields to types in corresponding columns
                for i in range(0, len(flds)):
                    column = columns[i]
                    c_type = column.Type()
                    if c_type in ('string', 'text'):
                        # do not use try/except here. Raise exception on error.
                        newObject = flds[i][:]
                    elif c_type == 'float':
                        newObject = float( flds[i].replace(',', '.') )
                    elif c_type == 'int':
                        newObject = int( flds[i] )
                    elif c_type == 'boolean':
                        newObject = not not int( flds[i] ) or None
                    elif c_type == 'date':
                        newObject = DateTime( flds[i] )
                    data[ column.getId() ] = newObject

                reg_num = None
                if data.has_key('ID'):
                    reg_num=data['ID']
                    del data['ID']

                message = self.addEntry( data=data, REQUEST=REQUEST, registry_id=reg_num )
                if message:
                    break

                interrupt_thread( self )

        if REQUEST is not None:
            return self.redirect( REQUEST=REQUEST, message=( message or "Entries added" ) )

    def _line_process( self, line, separator=';' ):
        fields = []
        line_pos = 0

        while line_pos < len(line):
            # Skip any space at the beginning of the field (if there should be leading space,
            #   there should be a " character in the CSV file)
            while line_pos < len(line) and line[line_pos] == " ":
                line_pos += 1
            field = ""
            quotes_level = 0
            while line_pos < len(line):
                # Skip space at the end of a field (if there is trailing space, it should be
                #   encompassed by speech marks)
                if not quotes_level and line[line_pos] == " ":
                    line_pos_temp = line_pos
                    while line_pos_temp < len(line) and line[line_pos_temp] == " ":
                        line_pos_temp += 1
                    if line_pos_temp >= len(line):
                        break
                    elif line[line_pos_temp] == separator:
                        line_pos = line_pos_temp
                if not quotes_level and line[line_pos] == separator:
                    break
                elif line[line_pos] == "\"":
                    quotes_level = not quotes_level
                else:
                    field = field + line[line_pos]
                line_pos += 1
            line_pos += len(separator)
            fields.append(field)
        if line[-len(separator)] == separator:
            fields.append(field)

        return fields

    security.declareProtected(CMFCorePermissions.View, 'resolveErrors')
    def resolveErrors( self, data=None, REQUEST=None ):
        """
            Helper function. Performs user's choice when error occured.
        """
        if data is None and REQUEST is not None:
            # Get entry info from REQUEST and place it into
            # the 'data' vocabulary
            data = self.parseEntryForm(self.listColumnIds(), REQUEST)
        #user's choice
        user_action = REQUEST is not None and REQUEST.get('user_action', '')
        source = self._getSourceObject(REQUEST=REQUEST)

        if not user_action:
            #abandon registration
            self.releaseSelectedDocument(redirect=0, REQUEST=REQUEST)
            ob = source or self
            return REQUEST['RESPONSE'].redirect( ob.absolute_url() )
        elif user_action == 'both':
            #register in both registries
            pr = getObjectByUid( self, self.getParentRegistry() )
            if pr is not None:
                return pr.addEntry( data, REQUEST, test_parent=0, childRegistry=self )
            else:
                #TODO: what to do if parent registry removed?
                raise "No parent registry object can be found."
        elif user_action == 'child':
            #register only in child registry (do not touch parent)
            return self.addEntry( data, REQUEST, test_parent=0 )
    #
    #   Entry implementation ======================================================================================
    #
    security.declareProtected( CMFCorePermissions.AddPortalContent, 'addEntry' )
    def addEntry( self, data=None, REQUEST=None, **kw ):
        """
            Adds new entry
        """
        self.lock.acquire()
        try:
            return self._addEntry( data, REQUEST, registry_id=kw.get('registry_id'),
                                   no_commit=kw.get('no_commit'),
                                   source=kw.get('source'),
                                   )
        finally:
            self.lock.release()

    security.declareProtected(CMFCorePermissions.AddPortalContent, 'editEntry')
    def editEntry( self, record_id, data=None, comment='', REQUEST=None, redirect=1 ):
        """
            Edits given entry
        """
        self.lock.acquire()
        try:
            return self._editEntry( record_id, data, comment, REQUEST, redirect )
        finally:
            self.lock.release()

    security.declareProtected(CMFCorePermissions.AddPortalContent, 'delEntries')
    def delEntries( self, selected_entries=None, REQUEST=None ):
        """
            Deletes entries
        """
        self.lock.acquire()
        try:
            self._delEntries( selected_entries or [], REQUEST )
        finally:
            self.lock.release()

    def _addEntry( self, data=None, REQUEST=None, test_parent=None, registry_id=None, childRegistry=None, \
                  no_commit=None, source=None ):
        """
            Adds row to the report table

            Arguments:

                'data' -- Column id:value mapping.

                'test_parent' -- Indicates if it should be tested that the document is registered
                                 in the parent registry, disabled.

                'registry_id' -- Value that will be stored in the 'ID' column. If None, it will
                                 be generated according registry settings.

                'childRegistry' -- Child registry (Registry) where it is needed to register
                                 given data too.
        """
        start_time = DateTime()
        uname = _getAuthenticatedUser(self).getUserName()
        catalog = getToolByName( self, 'portal_catalog', None )
        msg = getToolByName( self, 'msg', None )

        if data is None and REQUEST is not None:
            # Get entry info from REQUEST and place it into
            # the 'data' vocabulary
            data = self.parseEntryForm( self.listColumnIds(), REQUEST )
        if data is None:
            data = {}

        message = ''
        if source is None:
            source = self._getSourceObject( REQUEST=REQUEST )

        came_status = REQUEST is not None and REQUEST.get('came_status') or None
        IsTask = came_status and came_status[:4] == 'task' and 1 or 0
        if IsTask and source is not None:
            task = source
            source = task.getBase()
            uid = source.getUid()
        else:
            task = uid = None
            IsTask = 0

        IsRegistryFromData = 0
        counter = None
        IsError = 0

        if not no_commit:
            BeginThread( self, 'Registry.addEntry', force=1 )

        try:
            message = self.sanity_check_source( source, data, REQUEST )
            if message:
                raise SimpleError, message

            if registry_id is None:
                if data.has_key('ID') and data['ID']:
                    registry_id = data['ID']
                    IsRegistryFromData = 1
                else:
                    registry_id, counter = self._generate_registry_id( source )

            if not registry_id:
                message = 'Entry ID is not generated'
                raise SimpleError, message

            # check for duplicate registry_id (only in this registry)
            # the lack of this is that we don't check global duplicatiton of reg_ids.
            # but may be it is not needed - like in case with parent registry
            if IsRegistryFromData:
                x = self.check_dublicate_number( registry_id )
                if x:
                    message = 'Entry with given id already exists. $ %s $ error' % x
                    #message = 'Dublicate registry number $ %s $ error' % x
                    raise SimpleError, message

            # apply document ID and increment id counter
            data['ID'] = registry_id
            if 'SID' in self.listColumnIds():
                sid = self.getSIDById( registry_id )
                data['SID'] = sid
            if 'creation_date' in self.listColumnIds():
                data['creation_date'] = DateTime()

            entry = self._store( data, factory=RegistryEntry, counter=counter )

        except ( ConflictError, ReadConflictError ):
            raise

        except SimpleError, msg_error:
            message = '%s $ $ error' % str(msg_error)
            IsError = 1

        except Exception, msg_error:
            message = str(msg_error)
            logger.error('addEntry id: %s, message: %s' % ( registry_id, message ), exc_info=True)
            IsError = 1
            raise

        if not IsError and source is not None:
            message = 'Document was registered'
            if not hasattr( source, 'registry_data' ):
                source.registry_data = {}
            if source.registry_data.has_key( registry_id ):
                if self.getUid() not in source.registry_data[ registry_id ]:
                    source.registry_data[ registry_id ].append( self.getUid() )
            else:
                source.registry_data[ registry_id ] = [ self.getUid() ]

            setattr(source, 'modification_date', DateTime())
            source.manage_permission( ZopePermissions.delete_objects, [ Roles.Manager ], 0 )
            source._p_changed = 1

            if catalog is not None:
                catalog.reindexObject( source, idxs=REINDEX_IDXS, recursive=1 )
            else:
                source.reindexObject( idxs=REINDEX_IDXS )

            if childRegistry is None:
                self.releaseSelectedDocument( redirect=0, REQUEST=REQUEST )

            comment = self.make_system_comment( entry, comment='', source=source )
            if comment:
                entry.updateHistory( text=comment )
        else:
            if not message:
                message = 'Document was not registered by error $ $ error'

        if not IsError and IsTask:
            task.Respond( status=came_status, text=msg(message), redirect=0, no_commit=1, \
                no_update_runtime=1, force=1, REQUEST=REQUEST )

        if not no_commit:
            IsDone = CommitThread( self, 'Registry.addEntry', IsError, force=1, subtransaction=None )

            if IsDone == -1:
                message = '%s $ $ error' % ( 'Members weren\'t notified because of error' )

            end_time = DateTime()
            UpdateRequestRuntime( self, uname, start_time, end_time, 'Registry.addEntry' )

        portal_log( self, 'Registry', 'addEntry', 'source', ( source.physical_path(), getattr(source, 'registry_data', None), \
                uname, IsError, IsTask, message, self.physical_path() ), force=IsError )

        if REQUEST is not None:
            if source is not None:
                ob = source
            else:
                ob = self
            ob = UnrestrictedCheckObject( self, ob )
            if IsTask:
                #refreshClientFrame( ['workspace', 'followup_menu'] )
                params = { '_UpdateSections:tokens' : FollowupMenu }
                REQUEST['RESPONSE'].redirect( ob.absolute_url( message=message, params=params ) )
            else:
                REQUEST['RESPONSE'].redirect(ob.absolute_url( message=message ))

        if childRegistry is not None:
            childRegistry._addEntry( data=data, REQUEST=REQUEST, test_parent=0, registry_id=registry_id, \
                                     childRegistry=None )

        return IsError

    def _editEntry( self, record_id, data=None, comment='', REQUEST=None, redirect=1 ):
        """
            Edit row in the report table
        """
        start_time = DateTime()
        uname = _getAuthenticatedUser(self).getUserName()
        entry = self.getEntryById( record_id )
        entry.validate()
        message = ''
        IsError = 0

        BeginThread( self, 'Registry.editEntry', force=1 )

        if REQUEST is not None and data is None:
            # Get entry info from REQUEST and place it into the 'data' dictionary
            data = self.parseEntryForm(self.listColumnIds(), REQUEST)

        if REQUEST.has_key('ID') and not data.has_key('ID') and entry.isEditAllowed('ID'):
            data['ID'] = REQUEST.get('ID')

        registry_id = data.get('ID')

        # Do not allow to create entries with equal ID
        x = self.check_dublicate_number( registry_id, record_id )
        if x:
            message = "Entry with given id already exists. $ %s $ error" % x
            if REQUEST is not None:
                REQUEST['RESPONSE'].redirect( self.absolute_url( message=message ) )
            return

        if 'SID' in self.listColumnIds():
            SID = REQUEST.has_key('SID') and REQUEST.get('SID') or None
            id = data.get('ID') or entry.get('ID')
            sid = self.getSIDById( id )
            data['SID'] = ( SID != entry.get('SID') and SID or sid )

        if REQUEST.has_key('creation_date') and not data.has_key('creation_date') and entry.isEditAllowed('creation_date'):
            creation_date = parseDate( 'creation_date', REQUEST, None )
            data['creation_date'] = creation_date

        if _checkPermission(CMFCorePermissions.ModifyPortalContent, self):
            user = _getAuthenticatedUser(self).getUserName()
            entry_creator = REQUEST.get('entry_creator', entry._data.get('Creator', user))
            data['Creator'] = entry_creator

        try:
            if self._edit( data, record_id ):
                message = "Entry updated"

        except ( ConflictError, ReadConflictError ):
            raise

        except Exception, msg_error:
            logger.error('editEntry %s' % str(msg_error), exc_info=True)
            IsError = 1
            raise

        if not IsError:
            comment = self.make_system_comment( entry, comment=comment )
            if comment:
                entry.updateHistory( text=comment )

        CommitThread( self, 'Registry.editEntry', IsError, force=1, subtransaction=None )

        end_time = DateTime()
        UpdateRequestRuntime( self, uname, start_time, end_time, 'Registry.editEntry' )

        portal_log( self, 'Registry', 'editEntry', 'id', ( registry_id, uname, IsError, self.physical_path() ) )

        if redirect:
            if REQUEST is not None:
                REQUEST['RESPONSE'].redirect(self.absolute_url( message=message ))
        else:
            return true

    def make_system_comment( self, entry, comment='', source=None ):
        """
            Adds additional info for entry, correspondong objects url for instance
        """
        comment_template = '<font size=1 color="navy" style="font-style:normal;">%s</font>'

        if source is None:
            if not entry: return comment
            entry_info = self.listRegisteredDocumentsForEntry( entry )

            if not entry_info[1]:
                return comment
            for x in entry_info[1]:
                try:
                    ob = x.getObject()
                except:
                    continue
                if ob is not None and not ob.implements('isDocument'):
                    if comment:
                        comment += '<br>'
                    comment = comment + comment_template % ob.absolute_url()
        else:
            comment = comment + comment_template % source.absolute_url()

        return comment

    def _edit( self, entry_data, index ):
        """
            Edit registry entry
        """
        entry = self.getEntryById(index)
        reg_id = entry.get('ID')
        new_reg_id = entry_data.has_key('ID') and entry_data['ID']

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return None

        IsChanged = 0

        for key in entry_data.keys():
            if ( entry.isEditAllowed(key) or key == 'SID' ) and entry_data[key] != entry.get(key):
                if key == 'ID':
                    if not new_reg_id or reg_id == new_reg_id:
                        continue

                    res = catalog.unrestrictedSearch( registry_ids=reg_id, implements=IMPLEMENTS_FOR, sort_on='path' )

                    for r in res:
                        ob = r.getObject()
                        try:
                            ob.registry_ids()
                        except:
                            if ob is None:
                                logger.error('_editObject is None!')
                            else:
                                ob.registry_data = {}
                                logger.error("_edit bad registry_ids: %s" % ob.relative_url())
                            continue

                        registry_data = getattr( ob, 'registry_data', None ) or {}

                        if not registry_data:
                            pass
                        elif self.getUid() in registry_data.get(reg_id, []):
                            registry_data[reg_id].remove( self.getUid() )
                            if not registry_data[reg_id] or registry_data[reg_id] == []:
                                del registry_data[reg_id]
                            if new_reg_id in registry_data.keys():
                                if not self.getUid() in registry_data[new_reg_id]:
                                    registry_data[new_reg_id].append( self.getUid() )
                            else:
                                registry_data[new_reg_id] = [ self.getUid() ]
                            ob._p_changed = 1
                            logger.info("_edit registry_id was changed from %s to %s by %s. Object %s. Registry %s" % ( \
                                    reg_id, new_reg_id, _getAuthenticatedUser(self).getUserName(), ob.relative_url(), `self` \
                                ))

                        catalog.reindexObject( ob, idxs=REINDEX_IDXS, recursive=1 )

                entry.set( key, entry_data[key] )
                IsChanged = 1

        if IsChanged:
            self.catalog_object( entry, index )
            entry.notify_afterAdd()

        return IsChanged

    def _delEntries( self, selected_entries=None, REQUEST=None ):
        """
            Removes rows from the registry
        """
        if not selected_entries:
            return

        start_time = DateTime()
        uname = _getAuthenticatedUser(self).getUserName()
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return

        check_roles = [ Roles.Manager, Roles.Owner, Roles.Editor ]
        registry_ids = []
        IsError = -1

        BeginThread( self, 'Registry.delEntries', force=1 )

        for key in selected_entries:
            entry = self.getEntryById(key)
            if entry is None or not entry.isEntryDeleteAllowed():
                continue

            reg_id = entry.get('ID')
            res = catalog.unrestrictedSearch( registry_ids=reg_id, implements=IMPLEMENTS_FOR, sort_on='path' )

            try:
                for r in res:
                    ob = r.getObject()
                    if ob is None:
                        continue

                    registry_data = getattr( ob, 'registry_data', None ) or {}

                    if not registry_data:
                        pass
                    elif self.getUid() in registry_data.get(reg_id, []):
                        ob.registry_data[reg_id].remove( self.getUid() )
                        if not ob.registry_data[reg_id]:
                            del ob.registry_data[reg_id]
                        if not ob.registry_data:
                            ob.manage_permission(ZopePermissions.delete_objects, check_roles, 1)
                        ob._p_changed = 1

                    catalog.reindexObject( ob, idxs=REINDEX_IDXS, recursive=1 )

                registry_ids.append( reg_id )
                IsError = 0
            except KeyError, IndexError:
                IsError = 1
            
            self._remove( key )

        if IsError == -1 or not selected_entries:
            message = "Entris not selected"
            if REQUEST is not None:
                REQUEST['RESPONSE'].redirect(self.absolute_url( message=message ))
            else:
                return

        CommitThread( self, 'Registry.delEntries', IsError, force=1, subtransaction=None )

        end_time = DateTime()
        UpdateRequestRuntime( self, uname, start_time, end_time, 'Registry.delEntries' )

        portal_log( self, 'Registry', 'delEntries', 'ids', ( registry_ids, uname, IsError, `self` ) )

        message = "Entry deleted"
        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect(self.absolute_url( message=message ))
    #
    #   Custom API ===============================================================================================
    #
    security.declareProtected(CMFCorePermissions.View, 'sendExpiredNotification')
    def sendExpiredNotification( self, selected_entries=[], text=None, open_reports=1, REQUEST=None ):
        """
            Send notification to users who expired finalizing task
        """
        msg = getToolByName( self, 'msg', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        prptool = getToolByName( self, 'portal_properties', None )
        if None in ( msg, catalog, prptool, ):
            return

        if not text:
            text = msg('REPEATEDLY!') + '\n' + msg('Expiration message text')

        count = 0

        if not selected_entries:
            _entries = [ x.RecordId() for x in self.objectValues() ]
        else:
            _entries = selected_entries

        for key in _entries:
            entry = self.getEntryById(key)
            if entry is None:
                continue

            registry_id = entry.get('ID')
            docs = catalog.searchResults( registry_ids=registry_id, implements='isDocument' )

            for item in docs:
                ob = item.getObject()
                if ob is None:
                    continue
                if not self.isObjectRegistryIdValid( registry_id, ob ):
                    continue
                tasks = ob.hasExpiredTasks( show=1, returns='tasks' )
                if not tasks:
                    continue

                for task in tasks:
                    notify_users = task.getNotifyList( isclosed=None )
                    if notify_users:
                        task_text = text + '\n\n' + msg('Document') + ': ' + str(ob.Title()).strip()
                        if not task_text.endswith('.'):
                            task_text += '.'

                        count += task.KickUsers( selected_users=notify_users
                            , text=task_text
                            , open_reports=open_reports
                            , IsSystem=1
                            , REQUEST=None
                            )

                interrupt_thread( self )

        if count:
            message = "Expiration message was sent $ %s" % str(count)
        else:
            message = "Expiration is absent"

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect(self.absolute_url( message=message ))

    def CloneRegistry( self, uid ):
        """
            Makes a registry copy
        """
        if not uid:
            return
        source = getObjectByUid( self, uid )
        if source is None:
            return

        membername = _getAuthenticatedUser(self).getUserName()

        try:
            fields = source.listColumns()
        except:
            fields = []

        if fields:
            old_columns = self.listColumnIds()
            for id in old_columns:
                self.delColumn( id, remove_explicit=1 )

        reg_num_forming_rule = getattr( source, 'reg_num_forming_rule', None )
        is_allowed = source.isDelEntryAuthorAllowed()
        default_category = source.getDefaultCategory()
        department = source.getDepartment()

        new_columns = []

        for x in fields:
            id = x.getId()
            typ = x.Type()
            column = source.getColumnById( id )
            if column is None:
                continue

            title = column.Title()
            allows_input = getattr( column, 'allows_input', None )
            mandatory = column.isMandatory()
            editable = column.isEditableAfterReg()
            visible = column.isVisible()
            try:
                exportable = column.isExportable()
            except:
                exportable = None
            nowrap = column.isNowrap()
            system_field = column.getSystemFieldType()
            index_type = getattr( column, 'index_type', None )

            new_column_id = self.addColumn( id=id, title=title, typ=typ, allows_input=allows_input, \
                                            mandatory=mandatory, editable=editable, system_field=system_field, \
                                            index_type=index_type )

            try:
                new_column = self.getColumnById( new_column_id )
            except:
                continue

            setattr( new_column, 'exportable', exportable )
            setattr( new_column, 'visible', visible )
            setattr( new_column, 'nowrap', nowrap )

            new_columns.append( new_column_id )

        self.setDepartment( department )
        self.setDefaultCategory( default_category )
        self.setDelEntryAuthorAllowed( is_allowed )
        self.setRegNumFormingRule( reg_num_forming_rule )
        self.setCurrentRegistry()

        self.setup( force=1 )

        portal_log( self, 'Registry', 'CloneRegistry', 'source', ( uid, membername, new_columns, `source` ) )

    def DocumentAutoRegistration( self, object ):
        """
            Document auto registration
        """
        if object is None:
            return None
        if object.registry_ids():
            return 1
        category = object.getCategory()
        if category is None or not ObjectHasCustomCategory( object ):
            return None
        msg = getToolByName( self, 'msg', None )
        membership = getToolByName( self, 'portal_membership', None )
        if None in ( msg, membership, ):
            return None

        membername = _getAuthenticatedUser(self).getUserName()
        fields = self.listColumns()
        data = {}

        for x in fields:
            id = x.getId()
            typ = x.Type()
            column = self.getColumnById( id )
            if column is None or not column.allowsInput() or column.isComputed():
                continue

            try:
                attr = category.getAttributeDefinition( id )
                atype = attr.Type()
            except:
                continue

            value = object.getCategoryAttribute( id )
            attr_value = value != msg('nonselected') and value or ''

            if atype == typ:
                value = attr_value
            elif atype == 'lines' and typ == 'string':
                value = attr_value
            elif atype == 'link' and typ == 'string' and attr_value:
                value = getObjectByUid( self, attr_value ).getInfoForLink()
            elif atype == 'userlist' and typ == 'string':
                value = ', '.join( [ membership.getMemberName(user_id) or '' for user_id in attr_value ] )
            else:
                value = ''

            data[ id ] = value

        portal_log( self, 'Registry', 'DocumentAutoRegistration', 'data', data )
        IsError = data and self.addEntry( data=data, test_parent=0, no_commit=1, source=object ) or None

        return not IsError and 1 or 0
    #
    #   SID (entries sorting ID) =================================================================================
    #
    def checkSIDInfo( self, info ):
        """
            Checks info part like this: <pref>-.<subnumber>/<year>
        """
        info = re.sub( r'[-]', '', info )
        rexp = re.compile( r'([^\.]*)\.(\d*)\/(.*)', re.I+re.DOTALL )
        matched = rexp.search( info )
        if matched:
            x1 = info[ matched.start(1) : matched.end(1) ]
            x2 = info[ matched.start(2) : matched.end(2) ]
            x3 = info[ matched.start(3) : matched.end(3) ]
            info = '%s/%s.%s' % ( x1, x3, x2 )
        return info

    def getSIDParts( self, SID, order=None ):
        if order is None:
            order = self.getFpfxFormingRuleOrder()
        n = SID.find("/")

        if not order and n > 0:
            fpfx = ''
            number = None
            info = SID

            rule = self.reg_num_forming_rule
            r_seq = re.compile( r'(seq)\:?(\d+)?#?', re.I+re.DOTALL )
            m = r_seq.search( rule )

            if m:
                seq_begin = m.start(1) - 1
                if m.group(2):
                    seq_width = int(m.group(2))
                    number = SID[ seq_begin : seq_begin+seq_width ]
                elif seq_begin > -1:
                    number = ''
                    i = 0
                    while i < MAX_SIZE_OF_NUMBER and i < len( SID ):
                        try: s = SID[ seq_begin+i ]
                        except: break
                        if s not in '0123456789':
                            break
                        number += s
                        i += 1
                    seq_width = len( number )
                if number:
                    n = SID.find( number )
                    if len( SID ) > len( number ):
                        info = SID[ :n ] + SID[ n+seq_width: ]
                        info = self.checkSIDInfo( info )
                    else:
                        info = ''

        elif n == -1:
            fpfx = ''
            number = SID
            info = ''

        else:
            if order == 1:
                fpfx = SID[ :n ]
                number = SID[ n+1: ]
            elif order == 2:
                number = SID[ :n ]
                fpfx = SID[ n+1: ]

            delimiters = ( '/','-',':','.',' ', )
            info = ''

            for s in delimiters:
                n = number.find( s )
                if n > -1:
                    info = number[ n: ]
                    number = number[ :n ]
                    break

        return ( fpfx, number, info )

    def getSIDById( self, registry_id ):
        """
            Returns SID value by registry_id to run sorting.

            Arguments:

                'id' -- id of requisite field

            Result:

                String.
        """
        if not registry_id:
            return None

        RID = registry_id.strip()
        if len(RID) == 0:
            return None

        fpfx, number, info = self.getSIDParts( RID )

        if number:
            x = zfill( '0', MAX_SIZE_OF_NUMBER )
            sid = x + number
            number = sid[ -MAX_SIZE_OF_NUMBER : ]
            if fpfx or info:
                number = number + '/'
        else:
            number = ''

        #sid = number + fpfx + info
        sid = re.sub(r'(/)+', '/', number + fpfx + info)
        return sid

    def getNumberBySID( self, SID='', mode=None ):
        """
            Returns registry_id number part by SID value. SID is always in format: <number>{/<fpfx>{<info>}}.
            It's just order = 2.

            Arguments:

                'sid' -- SID of requisite field

                'mode' -- additional, if we want to get next ('down') or previous ('up') registry_id value

            Result:

                String.
        """
        if not SID or len(SID) == 0:
            return None

        fpfx, number, info = self.getSIDParts( SID, order=2 )

        x = zfill( '0', MAX_SIZE_OF_NUMBER )
        try:
            i = int( number )
        except:
            i = 0

        if mode == 'up':
            if i >= 10 ** MAX_SIZE_OF_NUMBER:
                return '9' * MAX_SIZE_OF_NUMBER
            if i < self._counter.getValue() - 1:
                s = x + str( i+1 )
                number = s[ -MAX_SIZE_OF_NUMBER : ]
        elif mode == 'down':
            if i <= 0:
                return '0'*MAX_SIZE_OF_NUMBER
            if i > 1:
                s = x + str( i-1 )
                number = s[ -MAX_SIZE_OF_NUMBER : ]
        else:
            s = x + number
            number = s[ -MAX_SIZE_OF_NUMBER : ]

        return number

InitializeClass(Registry)
