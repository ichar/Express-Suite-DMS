"""
Patches Tool
$Id: Patches.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 21/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Zope2
from zLOG import LOG, DEBUG, INFO, ERROR

import re
from cgi import escape
from sys import _getframe as getframe, exc_info
from types import MethodType, StringType, DictType, TupleType, ListType, IntType
from DateTime import DateTime

from Acquisition import aq_base, aq_get
from AccessControl import Unauthorized
from AccessControl.SecurityManagement import getSecurityManager, newSecurityManager, get_ident
from ExtensionClass import ExtensionClass #, PythonMethodType, ExtensionMethodType
from ThreadedAsync import register_loop_callback
from Products.CMFCore.utils import getToolByName, tuplize

import threading
from ZODB.POSException import ConflictError, ReadConflictError

# apply Nux patches before initialization of our classes
import Products.NuxUserGroups

# for Globals.get_request
import Products.Localizer

import Config
from ConflictResolution import ResolveConflict
from TransactionManager import AbortThread

from logging import getLogger
logger = getLogger( Config.ProductName )

MethodTypes = [ MethodType ]

# ================================================================================================================
#   Python PATCHES
# ================================================================================================================

logger.info( 'Patching Python __builtins__' )

import Missing
__builtins__['MissingValue'] = Missing.Value

try:
    True, False
except NameError:
    __builtins__['True']  = 1==1
    __builtins__['False'] = 1==0

try:
    bool(True)
except NameError:
    import operator
    __builtins__['bool'] = operator.truth
    del operator

try:
    StopIteration
except NameError:
    __builtins__['StopIteration'] = IndexError
except:
    pass

def safeIsInstance( object, klass ):
    try:
        if _old_isinstance( object, klass ):
            return True
    except TypeError:
        if type(klass) is TupleType:
            for item in klass:
                if safeIsInstance( object, item ):
                    return True
        return False
    try:
        return issubclass( object.__class__, klass )
    except ( AttributeError, TypeError ):
        return False

try:
    isinstance( None, ExtensionClass )
    isinstance( None, ( ExtensionClass, ) )
except TypeError: # python < 2.2
    __builtins__['_old_isinstance'] = isinstance
    __builtins__['isinstance'] = safeIsInstance

class MarkerValue:
    # Special 'marker' values class
    def __init__( self, name, value=False, builtin=True ):
        self.__name__ = name
        self.__value__ = value
        if builtin:
            __builtins__.setdefault( name, self )

    def __nonzero__( self ):
        return self.__value__

    def __repr__( self ):
        return self.__name__

    def __getstate__( self ):
        raise TypeError, "%s cannot be pickled" % repr(self)

# magical value to indicate omitted keyword arguments
# MarkerValue( 'Missing' )

# magical argument value to bypass security checks
# MarkerValue( 'Trust' )

# Python 2.1 getattr patch

GetattrMissing = MarkerValue( 'GetattrMissing', builtin=False )
def getattr_new( self, name, default=GetattrMissing ):
    try:
        return old_getattr( self, name )
    except AttributeError:
        if default is not GetattrMissing:
            return default
    raise AttributeError, name

class Temp:
   def __getattr__( self, n, d=None ):
       raise RuntimeError

try:
    getattr( Temp(), 'temp', 'temp' )
except RuntimeError:
    pass # good
else:
    if not __builtins__.has_key( 'old_getattr' ):
        logger.info( 'Patching getattr' )
        __builtins__['old_getattr'] = __builtins__['getattr']
    __builtins__['getattr'] = getattr_new

del Temp


# ================================================================================================================
#   DTML PATCHES
# ================================================================================================================
#   Registers new special formats of dtml-var:
#
#       'untaint' -- unquotes user-submitted values secured by ZPublisher
#       'checked', 'selected', 'disabled' -- renders specific html attributes
#       'jscript' -- escapes string values for use in JavaScript
#       'strip'   -- removes surrounding whitespace in the value
#       'class'   -- outputs class atribute if value is a non-empty string
#
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching DTML' )

from DocumentTemplate.DT_Var import special_formats

def untaint_format( v, name='(Unknown name)', md=None ):
    return str(v)

def checked_format( v, name='(Unknown name)', md=None ):
    return v and 'checked="1"' or ''

def selected_format( v, name='(Unknown name)', md=None ):
    return v and 'selected="1"' or ''

def disabled_format( v, name='(Unknown name)', md=None ):
    return v and 'disabled="1"' or ''

def jscript_format( v, name='(Unknown name)', md=None ):
    v = str(v).replace( '\\', '\\\\'    ).\
               replace( '\'', '\\\''    ).\
               replace( '\n', '\\n\\\n' ).\
               replace( '\r', ''        )
    return re.sub( r'</(script[^>]*)>', r'<\\057\1>', v, re.I )

def jscript_bool_format( v, name='(Unknown name)', md=None ):
    return v and 'true' or 'false'

def strip_format( v, name='(Unknown name)', md=None ):
    return str(v).strip()

def class_format( v, name='(Unknown name)', md=None ):
    return v and ('class="%s"' % escape(v, True)) or ''

special_formats['untaint'] = untaint_format
special_formats['checked'] = checked_format
special_formats['selected'] = selected_format
special_formats['disabled'] = disabled_format
special_formats['jscript'] = jscript_format
special_formats['jscript-bool'] = jscript_bool_format
special_formats['strip'] = strip_format
special_formats['class'] = class_format

# ------------------------------------------------------------------------------------------------------
#   Adds 'get', 'set', 'reduce', 'html_quote', 'url_quote' and 'url_quote_plus' functions to 
#   DTML builtins
# ------------------------------------------------------------------------------------------------------

from AccessControl.ZopeGuards import guarded_getitem
from DocumentTemplate.DT_Util import TemplateDict, NotBindable, safe_callable
from DocumentTemplate.DT_Var import html_quote, url_quote, url_quote_plus

def guarded_reduce( f, seq, init=MissingValue ):
    safe_seq = []
    for idx in range(len(seq)): # use enumerate in python 2.3
        item = guarded_getitem(seq, idx)
        safe_seq.append(item)
    if init is MissingValue:
        return reduce(f, safe_seq)
    return reduce(f, safe_seq, init)

def TemplateDict_get( self, key, default=None, call=False ):
    try:
        return self.getitem( key, call )
    except KeyError:
        return default

def TemplateDict_set( self, key, value ):
    stack = []
    data = last_dict = None
    while True:
        try:
            stack.append( self._pop() )
        except IndexError:
            break
        if not isinstance( stack[-1], DictType ):
            if data is None:
                data = last_dict
            continue
        last_dict = stack[-1]
        if last_dict.has_key( key ):
            data = last_dict
            break
    while stack:
        self._push( stack.pop() )
    if data is None:
        raise TypeError, self
    data[ key ] = value

TemplateDict.get = TemplateDict_get
TemplateDict.set = TemplateDict_set
TemplateDict.reduce = NotBindable( guarded_reduce )
TemplateDict.html_quote = NotBindable( html_quote )
TemplateDict.url_quote = NotBindable( url_quote )
TemplateDict.url_quote_plus = NotBindable( url_quote_plus )

# ------------------------------------------------------------------------------------------------------
#   Enables dtml-in tag to use methods as sorting keys
# ------------------------------------------------------------------------------------------------------
"""
from DocumentTemplate import DT_In

def DT_In_basic_type( value ):
    try:
        return DT_In._nau_basic_type( value )
    except TypeError:
        return False

try:
    DT_In.basic_type( {}.get )
except TypeError:
    DT_In._nau_basic_type = DT_In.basic_type
    DT_In.basic_type = DT_In_basic_type
"""


# ================================================================================================================
#   Python Script PATCHES
# ================================================================================================================
#
#   1. Adds 'True' and 'False' values to Python Script and DTML builtins.
#
#   2. Adds 'reduce' functions to Python Script builtins.
#
#   3. Adds 'values' method to python scripts -- returns actual script parameters as a dictionary.
#
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching PythonScript' )

from AccessControl import safe_builtins
from RestrictedPython.Eval import RestrictionCapableEval
from Products.PythonScripts import PythonScript
from Products.CMFCore.FSPythonScript import FSPythonScript

RestrictionCapableEval.globals['True'] = True
RestrictionCapableEval.globals['False'] = False

safe_builtins['True'] = True
safe_builtins['False'] = False

safe_builtins['reduce'] = guarded_reduce
PythonScript.safe_builtins = safe_builtins

PythonScript = PythonScript.PythonScript

def pythonscript_values( self, **kw ):
    res = {}
    vars = getframe(1).f_locals
    skip = ['self','REQUEST']

    for name in self.params().split(','):
        name = name.split('=', 1)[0].strip()
        if name not in skip and vars.has_key( name ):
            res[ name ] = vars[ name ]

    res.update( kw )
    return res

PythonScript.values = pythonscript_values
FSPythonScript.values = pythonscript_values


# ================================================================================================================
#   Zope Security PATCHES
# ================================================================================================================
#   1. Modifies newSecurityManager function to preserve SecurityContext stack during authorization process, but 
#      only if the new user is the same as the old one, or if the user is just getting authenticated.
#
#   2. Relaxes SecurityManager.addContext behaviour -- increase stack only if new context is an owned object or 
#      has proxy roles set on it; in particular, filesystem-based objects bypass this restriction.
#
#   Required for ProxyAccessProvider.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching SecurityManagement' )

from AccessControl import SecurityManagement
from AccessControl import SpecialUsers
from AccessControl import User
from AccessControl.PermissionRole import rolesForPermissionOn
from AccessControl.SecurityManager import SecurityManager
from AccessControl.SecurityManagement import SecurityContext, _managers as SecurityManagers

def security_newSecurityManager( request, user ):
    # Set up a new security context for a request for a user
    thread_id = get_ident()
    security = SecurityManagers.get( thread_id, None )
    #print '@@@ in newSecurityManager', thread_id, (hasattr(security,'_context') and security._context.stack or '-')

    if security is not None:
        #print '@@@', thread_id, security._context.user, user
        old = aq_base( security._context.user )
        if old is aq_base( user ):
            return
        if old is SpecialUsers.nobody:
            security._context.user = user
            for context in security._context.stack:
                try: context.securityUserChanged()
                except AttributeError: pass
            return

    #print '@@@ creating new SecurityManager'
    SecurityManagers[ thread_id ] = SecurityManager( thread_id, SecurityContext(user), )

SecurityManagement.newSecurityManager = security_newSecurityManager
User.newSecurityManager = security_newSecurityManager
Zope2.App.startup.newSecurityManager = security_newSecurityManager

def sm_setSecurityManager( manager ):
    #
    # Install *manager* as current security manager for this thread
    #
    thread_id = get_ident()
    old = SecurityManagers.get( thread_id, None )
    SecurityManagers[ thread_id ] = manager
    return old

if not hasattr(SecurityManagement,'setSecurityManager'):
    SecurityManagement.setSecurityManager = sm_setSecurityManager

def security_addContext( self, object, force=None ):
    #print 'security_addContext'
    if not force:
        base = aq_base( object )
        force = getattr( base, '_owner', None ) is not None
        force = force or getattr( base, '_proxy_roles', None )
    if force:
        #print '@@@ addContext', getattr(object, 'id', ''), type(aq_base(object)), object.getOwner()
        self._security_addContext( object )

if not hasattr( SecurityManager, '_security_addContext' ):
    SecurityManager._security_addContext = SecurityManager.addContext

SecurityManager.addContext = security_addContext

# ----------------------------------------------------------------------------------------------------------------
#   1. Adds proxy roles and executable owner checking to checkPermission for ProxyAccessProvider.
#
#   2. Prevents VersionableRoles from merging versionable content local roles with local roles of the currently 
#      selected version, thus we can safely check version objects for permissions.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching ZopeSecurityPolicy' )

from AccessControl.ZopeSecurityPolicy import ZopeSecurityPolicy

def zope_checkPermission( self, permission, object, context ):
    roles = rolesForPermissionOn( permission, object )
    if type(roles) is StringType:
        roles = [ roles ]

    versionable = None
    if hasattr( aq_base(object), 'implements') and object.implements('isVersion'):
        versionable = object.getVersionable()
    if versionable is not None:
        versionable._v_disable_versionable_roles = 1

    try:
        result = context.user.allowed( object, roles )
    finally:
        if hasattr( versionable, '_v_disable_versionable_roles' ):
            del versionable._v_disable_versionable_roles

    if not result:
        # try proxy roles
        if self._checkProxyRoles( object, roles, context ):
            result = 1

    return result

def zope_checkProxyRoles( self, object, roles, context ):
    if not context.stack:
        return 0

    eo = context.stack[-1]
    proxy_roles = getattr( eo, '_proxy_roles', None )
    if not proxy_roles:
        return 0

    # If the executable had an owner, can it execute?
    if getattr( self, '_ownerous', 1 ):
        owner = eo.getOwner()
        if (owner is not None) and not owner.allowed( object, roles ):
            return 0

    for r in proxy_roles:
        if r in roles:
            return 1

    return 0

ZopeSecurityPolicy.checkPermission = zope_checkPermission
ZopeSecurityPolicy._checkProxyRoles = zope_checkProxyRoles

# ----------------------------------------------------------------------------------------------------------------
#   The same as above, but for _checkPermission in CMFCore.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching CMFCore Security' )

from Products.CMFCore import utils as CMFCoreUtils

def cmfcore_checkPermission( permission, object ):
    roles = rolesForPermissionOn( permission, object )
    if type(roles) is StringType:
        roles = [ roles ]

    # XXX Dummy hack to prevent VersionableRoles from merging versionable content
    # local roles with local roles of the currently selected version, thus we can
    # safely check version objects for permissions.

    versionable = None
    if hasattr( aq_base(object), 'implements') and object.implements('isVersion'):
        versionable = object.getVersionable()
    if versionable is not None:
        versionable._v_disable_versionable_roles = 1
    try:
        security = getSecurityManager()
        result = security.getUser().allowed( object, roles )

    finally:
        if hasattr( versionable, '_v_disable_versionable_roles' ):
            del versionable._v_disable_versionable_roles

    if not result:
        # try proxy roles
        #print '######', security._context.user, security._context.stack
        if security._policy._checkProxyRoles( object, roles, security._context ):
            result = 1

    return result

CMFCoreUtils._checkPermission = cmfcore_checkPermission

# ----------------------------------------------------------------------------------------------------------------
#   Security performance optimization -- when gathering permission names from the class inheritance, cache result 
#   and return it on subsequent calls. Speeds up content creation and copying.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching Role' )

from AccessControl import Role
from Products.DCWorkflow import utils as DCWorkflowUtils

def role_gather_permissions( klass, result, seen ):
    cache = klass.__dict__.get('__ac_permissions_cache__')

    if cache is None:
        cache = {}
        bases = list( klass.__bases__ )
        while bases:
            base = bases.pop(0)
            perms = base.__dict__.get('__ac_permissions_cache__')
            if perms is not None:
                cache.update( perms )
            else:
                perms = base.__dict__.get('__ac_permissions__')
                if perms is not None:
                    for p in perms:
                        cache.setdefault( p[0], (p[0], ()) )
                bases = list( base.__bases__ ) + bases
        klass.__ac_permissions_cache__ = cache

    for name, value in cache.items():
        if not seen.has_key( name ):
            seen[ name ] = None
            result.append( value )

    return result

Role.gather_permissions = role_gather_permissions
CMFCoreUtils.gather_permissions = role_gather_permissions
DCWorkflowUtils.gather_permissions = role_gather_permissions

# ----------------------------------------------------------------------------------------------------------------
#   Fixes missing BasicGroup.getId method, adds new isReadOnly method, and sets up reasonable attribute access.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching BasicGroup' )

from AccessControl import ClassSecurityInfo
from OFS.SimpleItem import Item
from Products.NuxUserGroups.UserFolderWithGroups import BasicGroup

# must have clear name for __roles__ to be accessible
def isReadOnly( self ):
    return 0

def isUsersStorage( self ):
    return 0

def getId( self ):
    # Returns the identifier of the object
    id = self.id
    if id is not None and callable( id ):
        return id()
    return id

BasicGroup.getId = getId #Item.getId
BasicGroup.isReadOnly = isReadOnly
BasicGroup.isUsersStorage = isUsersStorage

security = ClassSecurityInfo()
security.declarePublic( 'getId', 'isReadOnly', 'isUsersStorage', 'Title' )

# this basically removes security declaration for Title
perms = []
skip = lambda name, has=security.names.has_key: not has(name)
for item in BasicGroup.__ac_permissions__:
    perms.append( item[:1] + (filter( skip, item[1] ),) + item[2:] )
BasicGroup.__ac_permissions__ = tuple(perms)

security.apply( BasicGroup )

# ----------------------------------------------------------------------------------------------------------------
#   Change user with groups
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching UserFolderWithGroups' )

from AccessControl.User import UserFolder
from Products.NuxUserGroups.UserFolderWithGroups import UserFolderWithGroups

def _doChangeUser( self, name, password, roles, domains, groups=MissingValue, **kw ):
    apply(UserFolder._doChangeUser, ( self, name, password, roles, domains ), kw)
    if groups is not MissingValue:
        self.setGroupsOfUser(groups, name)

UserFolderWithGroups._doChangeUser = _doChangeUser


# ================================================================================================================
#   Object Manager PATCHES
# ----------------------------------------------------------------------------------------------------------------
logger.info( 'Patching OFS' )

from OFS.PropertySheets import PropertySheet

def sheet_p_resolveConflict( self, oldState, savedState, newState ):
    #
    # Try to resolve conflict between container's objects
    #
    return 1

PropertySheet._p_resolveConflict = sheet_p_resolveConflict

"""
from OFS.ObjectManager import ObjectManager, BeforeDeleteException

def OFS_manage_beforeDelete( self, item, container ):
    for object in self.objectValues():
        try: s = object._p_changed
        except: s = 0
        try:
            if hasattr(aq_base(object), 'manage_beforeDelete'):
                object.manage_beforeDelete( item, container )
        except ( ConflictError, ReadConflictError ):
            raise
        except BeforeDeleteException, ob:
            raise
        except:
            logger.error('Zope2 manage_beforeDelete() threw', exc_info=True)

        if s is None: object._p_deactivate()

def OFS_delObject( self, id, dp=1 ):
    try:
        object = self._getOb( id )
        object.manage_beforeDelete( object, self )
    except ( ConflictError, ReadConflictError ):
        raise
    except BeforeDeleteException, ob:
        raise
    except:
        logger.error('Zope2 manage_beforeDelete() threw', exc_info=True)

    self._objects = tuple(filter( lambda i, n=id: i['id'] != n, self._objects ))
    self._delOb( id )

    # Indicate to the object that it has been deleted. This is
    # necessary for object DB mount points. Note that we have to
    # tolerate failure here because the object being deleted could
    # be a Broken object, and it is not possible to set attributes
    # on Broken objects.
    try: object._v__object_deleted__ = 1
    except: pass

ObjectManager.manage_beforeDelete = OFS_manage_beforeDelete
ObjectManager._delObject = OFS_delObject
"""


# ================================================================================================================
#   Zope Publisher PATCHES
# ================================================================================================================
#   Allows for portal object to define _afterValidateHook callback method, which will be called during HTTP 
#   request processing, right after the user is authenticated and becomes known.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching Zope2.zpublisher_validated_hook' )

def zpublisher_validated_hook( self, user ):
    if Zope2 is None:
        return

    Zope2._old_zpublisher_validated_hook( self, user )

    try:
        published = self.PUBLISHED
        if type(published) in MethodTypes:
            published = published.im_self
        portal = published.getPortalObject()
    except AttributeError:
        pass
    else:
        if hasattr( portal, '_afterValidateHook' ):
            portal._afterValidateHook( user, published, REQUEST=self )

def install_validated_hook( *args ):
    if not hasattr( Zope2, '_old_zpublisher_validated_hook' ):
        logger.info( 'Patching ZPublisher validated_hook' )
        Zope2._old_zpublisher_validated_hook = Zope2.zpublisher_validated_hook
        Zope2.zpublisher_validated_hook = zpublisher_validated_hook

if hasattr( Zope2, '_old_zpublisher_validated_hook' ):
    logger.info( 'Patching ZPublisher validated_hook' )
    Zope2.zpublisher_validated_hook = zpublisher_validated_hook
else:
    logger.info( 'Registering callback' )
    register_loop_callback( install_validated_hook )

# ----------------------------------------------------------------------------------------------------------------
#   Changes existing type converters: 'lines' -- line values
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching ZPublisher Converters' )

from ZPublisher.Converters import field2text, type_converters

def converters_field2lines(v):
    if type(v) in (ListType, TupleType):
        return map( str, v )
    return field2text(v).splitlines()

type_converters['lines'] = converters_field2lines


# ================================================================================================================
#   CMFCore PATCHES
# ================================================================================================================

logger.info( 'Patching CMFDefault' )

from Products.CMFDefault.Document import Document
from Products.CMFDefault.exceptions import EditingConflict
from StructuredText.StructuredText import HTML

def default_CookedBody( self, stx_level=None, setlevel=0 ):
    #
    # Removed cooked_body
    #
    if (self.text_format == 'html' or self.text_format == 'plain'
        or (stx_level is None)
        or (stx_level == self._stx_level)):
        return self.cooked_text or self.text
    else:
        cooked = HTML(self.text, level=stx_level, header=0)
        if setlevel:
            self._stx_level = stx_level
            self.cooked_text = cooked
        return cooked

Document.CookedBody = default_CookedBody

def default_edit( self, text, text_format='', safety_belt='' ):
    #
    # Edit the Document and cook the body
    #
    if not self._safety_belt_update(safety_belt=safety_belt):
        msg = ("Intervening changes from elsewhere detected."
               " Please refetch the document and reapply your changes."
               " (You may be able to recover your version using the"
               " browser 'back' button, but will have to apply them"
               " to a freshly fetched copy.)")
        raise EditingConflict(msg)

    self.text = text
    self._size = len(text)

    if not text_format:
        text_format = self.text_format
    if text_format == 'html':
        pass #self.cooked_text = text
    elif text_format == 'plain':
        self.cooked_text = html_quote(text).replace('\n', '<br />')
    else:
        self.cooked_text = HTML(text, level=self._stx_level, header=0)

Document._edit = default_edit

from Products.CMFCore.FSDTMLMethod import FSDTMLMethod

def default_validate( self, inst, parent, name, value, md=None ):
    #
    # CMFCore FSDTMLMethod authorizing validation
    #
    id = self.getId()
    #if id == 'folder' and name in ( \
    #         'getObject','getURL','is_directive','meta_type','category','state','context',
    #         'nd_uid','None','hide_buttons','id','Title','this','isRoot','ZopeTime', ):
    #    return 1
    try:
        p = getSecurityManager().validate( inst, parent, name, value )
    except Unauthorized, message:
        roles = getattr(inst, '__roles__', None)
        #logger.info("validate is Unauthorized id: %s, name: %s, inst:\n%s\nroles: %s" % ( id, name, inst, roles ))
        LOG('Patches.default_validate', DEBUG, "validate is Unauthorized id: %s, name: %s, inst:\n%s\nroles: %s" % ( \
                id, name, inst, roles ))
        #logger.info( message )
        raise
    return p

FSDTMLMethod.validate = default_validate


# ================================================================================================================
#   ZCatalog PATCHES
# ================================================================================================================

logger.info( 'Patching CMFCatalogAware' )

from Products.CMFCore.CMFCatalogAware import CMFCatalogAware

security = ClassSecurityInfo()
security.declarePublic( 'reindexObject', 'reindexObjectSecurity' )

# this basically removes security declaration for 'reindexObject', 'reindexObjectSecurity'
perms = []
skip = lambda name, has=security.names.has_key: not has(name)
for item in CMFCatalogAware.__ac_permissions__:
    perms.append( item[:1] + (filter( skip, item[1] ),) + item[2:] )
CMFCatalogAware.__ac_permissions__ = tuple(perms)

security.apply( CMFCatalogAware )

"""
def CMFCatalogAware_indexObject( self ):
    #
    # Index the object in the portal catalog.
    # Check content meta type before. Don't catalog unindexable contents
    #
    meta_type = getattr(self, 'meta_type', None)
    try:
        if not meta_type or meta_type in Config.UnindexableContents:
            logger.info('unindexable content: %s' % `self`)
            return
    except:
        logger.error('unindexable content: %s' % `self`, exc_info=True)
    self._indexObject()

if not hasattr( CMFCatalogAware, '_indexObject' ):
    CMFCatalogAware._indexObject = CMFCatalogAware.indexObject

CMFCatalogAware.indexObject = CMFCatalogAware_indexObject

def CMFCatalogAware_unindexObject( self ):
    #
    # UnIndex the object in the portal catalog.
    # Check content meta type before. Don't uncatalog unindexable contents
    #
    meta_type = getattr( self, 'meta_type', None )
    try:
        if not meta_type or meta_type in Config.UnindexableContents:
            logger.info( 'unindexable content: %s' % `self`)
            return
    except:
        logger.error( 'unindexable content: %s' % `self`, exc_info=True)
    self._unindexObject()

if not hasattr( CMFCatalogAware, '_unindexObject' ):
    CMFCatalogAware._unindexObject = CMFCatalogAware.unindexObject

CMFCatalogAware.unindexObject = CMFCatalogAware_unindexObject
"""

# ----------------------------------------------------------------------------------------------------------------
#   1. ZCatalog performance optimization -- uses fast multiunion instead of a loop to merge subsets into resulting
#      set. Speeds up queries utilizing 'effective' index.
#
#   2. Adds 'not' operator for index queries (still rather slow and memory expensive).
#
#   3. Adds 'operator' to query options to Field and Date Indexes.
# ----------------------------------------------------------------------------------------------------------------
"""
from BTrees.IIBTree import IISet, IITreeSet, union, intersection, difference
from BTrees.IOBTree import IOBTree
from Products.PluginIndexes.common.UnIndex import UnIndex
from Products.PluginIndexes.common.util import parseIndexRequest
from Products.PluginIndexes.FieldIndex.FieldIndex import FieldIndex
from Products.PluginIndexes.DateIndex.DateIndex import DateIndex
from Products.PluginIndexes.PathIndex.PathIndex import PathIndex

logger.info( 'Patching ZCatalog performance optimization' )

try:
    from BTrees.IIBTree import multiunion
except ImportError: # Zope < 2.6
    multiunion = None

if multiunion is None:
    def multiunion( seq ):
        return reduce( union, seq, None )

def multiintersection( seq ):
    return reduce( intersection, seq, None )

def unindex_apply_index( self, request, cid='' ):
    if isinstance( request, parseIndexRequest ):
        record = request
    else:
        record = parseIndexRequest(request, self.id, self.query_options)

    if record.keys is None:
        return None

    index = self._index
    r = opr = None

    # experimental code for specifing the operator
    operator = record.get('operator', self.useOperator)
    if not operator in self.operators:
        if operator in ['not', 'and_not', 'or_not'] and self.meta_type in [ \
                'FieldIndex', 'DateIndex', 'KeywordIndex' ]:
            self.operators = tuple( self.operators ) + ( operator, )
        else:
            raise RuntimeError, "operator not valid: %s" % escape(operator)

    # depending on the operator we use intersection or union
    if operator.startswith('and'):
        set_func = intersection
        multi_set_func = multiintersection
    else:
        set_func = union
        multi_set_func = multiunion

    # Range parameter
    range_parm = record.get('range')
    if range_parm:
        opr = 'range'
        opr_args = []
        if range_parm.find('min') > -1:
            opr_args.append('min')
        if range_parm.find('max') > -1:
            opr_args.append('max')

    if record.get('usage'):
        # see if any usage params are sent to field
        opr = record.usage.lower().split(':')
        opr, opr_args=opr[0], opr[1:]

    if opr == 'range':   # range search
        if 'min' in opr_args:
            lo = min(record.keys)
        else:
            lo = None
        if 'max' in opr_args:
            hi = max(record.keys)
        else:
            hi = None

        r = multi_set_func( index.values(lo,hi) )

    else: # not a range search
        for key in record.keys:
            r = set_func( r, index.get(key, IISet()) )

    if operator.endswith('not'):
        r = difference( IISet(self._unindex.keys()), r )

    if r is None:
        r = IISet()
    elif isinstance( r, IntType ):
        r = IISet([r])

    return r, (self.id,)

UnIndex._apply_index = unindex_apply_index
"""
# ----------------------------------------------------------------------------------------------------------------
#   DateIndex implementation
# ----------------------------------------------------------------------------------------------------------------
"""
logger.info( 'Patching ZCatalog DateIndex' )

def dateindex_apply_index( self, request, cid='' ):
    record = parseIndexRequest(request, self.id, self.query_options)
    if record.keys is None: return None

    record.keys = map( self._convert, record.keys )

    return UnIndex._apply_index( self, record, cid=cid)

DateIndex._apply_index = dateindex_apply_index

for Index in [ FieldIndex, DateIndex ]:
    if 'operator' not in Index.query_options:
        Index.query_options.append( 'operator' )
"""
# ----------------------------------------------------------------------------------------------------------------
#   PathIndex implementation
# ----------------------------------------------------------------------------------------------------------------
"""
logger.info( 'Patching ZCatalog PathIndex' )

def pathindex_insertEntry( self, comp, id, level ):
    # Insert an entry.
    #
    # comp is a path component 
    # id is the docid
    # level is the level of the component inside the path.
    #
    # Patched to use IITreeSet.

    index = self._index
    if not index.has_key(comp):
        index[comp] = IOBTree()

    if not index[comp].has_key(level):
        index[comp][level] = IITreeSet()

    index[comp][level].insert(id)

    if level > self._depth:
        self._depth = level

def pathindex_index_object( self, docid, obj, threshold=100 ):
    ''' hook for (Z)Catalog '''

    # PathIndex first checks for an attribute matching its id and
    # falls back to getPhysicalPath only when failing to get one.
    # The presence of 'indexed_attrs' overrides this behavior and
    # causes indexing of the custom attribute.

    attrs = getattr(self, 'indexed_attrs', None)
    if attrs:
        index = attrs[0]
    else:
        index = self.id

    f = getattr(obj, index, None)
    if f is not None:
        if safe_callable(f):
            try:
                path = f()
            except AttributeError:
                return 0
        else:
            path = f

        if not isinstance(path, (StringType, TupleType)):
            raise TypeError('path value must be string or tuple of strings')
    else:
        try:
            path = obj.getPhysicalPath()
        except AttributeError:
            return 0

    if isinstance(path, (ListType, TupleType)):
        comps = filter(None, path)
        path = '/'.join(path)
    elif isinstance( path, StringType ):
        comps = filter(None, path.split('/') )
    else:
        raise TypeError( path )

    len_comps = len( comps )

    # Make sure we reindex properly when path change
    if self._unindex.get(docid, path) != path:
        self.unindex_object(docid)

    # 2.7 Index length Support 
    #if not self._unindex.has_key(docid):
    #    if hasattr(self, '_migrate_length'):
    #        self._migrate_length()
    #    self._length.change(1)

    for i in range(len_comps): # enumerate in python 2.3
        self.insertEntry(comps[i], docid, i)

    # Add terminator
    self.insertEntry(None, docid, len_comps-1)

    # XXX
    if not path.startswith('/'): path = '/'+path

    self._unindex[docid] = path
    return 1

def pathindex_unindex_object( self, docid ):
    ''' hook for (Z)Catalog '''

    if not self._unindex.has_key(docid):
        logger.error( 'Patches.PathIndex Attempt to unindex nonexistent document with id %s' % docid )
        return

    # There is an assumption that paths start with /
    path = self._unindex[docid]

    # redundant
    # if not path.startswith('/'): path = '/'+path

    comps = filter( None, path.split('/') )
    len_comps = len( comps )

    def unindex(comp, level, index=self._index, docid=docid):
        try:
            index[comp][level].remove(docid)

            if not index[comp][level]:
                del index[comp][level]

            if not index[comp]:
                del index[comp]
        except KeyError:
            logger.error( 'Patches.PathIndex Attempt to unindex document with id %s failed at level'
                                   ' %s' % (docid, level) )

    for level in range(len_comps):
        unindex(comps[level], level)

    # Remove the terminator
    unindex( None, len_comps - 1 )

    # 2.7 Index length Support 
    #if hasattr(self, '_migrate_length'):
    #    self._migrate_length()
    #  self._length.change(-1)

    del self._unindex[docid]

def pathindex_search( self, path, default_level=0, depth=0 ):
    # path is either a string representing a
    # relative URL or a part of a relative URL or
    # a tuple (path,level).
    #
    # level >= 0  starts searching at the given level
    # level <  0  search on all levels
    #
    # depth if greater then zero search only down to a depth value.

    assert isinstance( depth, IntType), `depth`

    if isinstance(path, StringType):
        startlevel = default_level
    else:
        path = path[0]
        startlevel = int(path[1])

    comps = filter(None, path.split('/'))
    len_comps = len( comps )

    if not len_comps and not depth:
        return IISet(self._unindex.keys())

    index = self._index
    results = None

    startlevels = startlevel >= 0 and [startlevel] or range(self._depth + 1)

    for startlevel in startlevels:
        ids = None
        for level in range(startlevel, startlevel + len_comps):
            comp = comps[level-startlevel]
            try:
                ids = intersection(ids, index[comp][level])
            except KeyError:
                break # path not founded
        else:
            if depth:
                endlevel = startlevel + len_comps - 1
                try:             
                    depthset = multiunion( index[None].values( endlevel, endlevel + depth ) )
                except KeyError:
                    pass
                else:
                    ids = intersection( ids, depthset )
            results = union( results, ids )

    return results or IISet()

def pathindex_apply_index( self, request, cid='' ):
     ''' hook for (Z)Catalog '''

     # 'request' --  mapping type (usually {"path": "..." }
     #  additionaly a parameter "path_level" might be passed
     #  to specify the level (see search())
     # 'cid' -- ???

     record = parseIndexRequest(request,self.id,self.query_options)
     if record.keys == None: return None

     level = record.get('level',0)
     operator = record.get('operator',self.useOperator).lower()
     depth = record.get('depth', 0)

     # depending on the operator we use intersection of union
     if operator == "or": set_func = union
     else: set_func = intersection

     res = None
     for k in record.keys:
         rows = self.search(k, level, depth)
         res = set_func(res,rows)

     return res or IISet(), (self.id,)

PathIndex.insertEntry = pathindex_insertEntry
PathIndex.index_object = pathindex_index_object
PathIndex.unindex_object = pathindex_unindex_object
PathIndex.search = pathindex_search
PathIndex._apply_index = pathindex_apply_index

for Index in [ PathIndex ]:
    for name in [ 'depth' ]:
        if name not in Index.query_options:
            Index.query_options = tuple(Index.query_options) + ( name, )
"""
# ----------------------------------------------------------------------------------------------------------------
#   Enable AttributesIndex sorting feature by means of using special sort index returned by getSortIndex.
# ----------------------------------------------------------------------------------------------------------------
"""
logger.info( 'Patching ZCatalog getSortIndex' )

from Products.ZCatalog.Catalog import Catalog, CatalogError

def Catalog_getSortIndex(self, args):
    #
    # Returns a search index object or None
    #
    sort_index_name = self._get_sort_attr("on", args)
    if sort_index_name is not None:
        # self.indexes is always a dict, so get() w/ 1 arg works
        sort_index = self.indexes.get(sort_index_name)
        if sort_index is None:
            raise CatalogError, 'Unknown sort_on index'
        else:
            if hasattr(sort_index, 'getSortIndex'):
                sort_index = sort_index.getSortIndex(args)

            if not hasattr(sort_index, 'keyForDocument'):
                raise CatalogError(
                    'The index chosen for sort_on is not capable of being'
                    ' used as a sort index.'
                    )
        return sort_index
    else:
        return None

Catalog._getSortIndex = Catalog_getSortIndex
"""
# ----------------------------------------------------------------------------------------------------------------
#   Previous Unindex.
#   Note! We should use either it or a code above.
# ----------------------------------------------------------------------------------------------------------------
"""
logger.info( 'Patching ZCatalog UnIndex' )

from Products.PluginIndexes.common.UnIndex import UnIndex, _marker as unindex_marker

def unindex_unindex_object( self, documentId ):
    # Unindex the object with integer id 'documentId' and don't
    # raise an exception if we fail
    unindexRecord = self._unindex.get(documentId, unindex_marker)
    if unindexRecord is unindex_marker:
        return None

    self.removeForwardIndexEntry(unindexRecord, documentId)

    try:
        del self._unindex[documentId]
    except:
        #logger.error( 'Patches.UnIndex Attempt to unindex nonexistent document with id %s' % documentId )
        pass

UnIndex.unindex_object = unindex_unindex_object

from Products.PluginIndexes.KeywordIndex import KeywordIndex

def keywordindex_unindex_object( self, documentId ):
    # carefully unindex the object with integer id 'documentId'
    keywords = self._unindex.get(documentId, None)
    self.unindex_objectKeywords(documentId, keywords)
    try:
        del self._unindex[documentId]
    except KeyError:
        #logger.error( 'Patches.KeywordIndex Attempt to unindex nonexistent document id %s' % documentId )
        pass

KeywordIndex.unindex_object = keywordindex_unindex_object

from Products.PluginIndexes.PathIndex import PathIndex

def pathindex_unindex_object( self, documentId ):
    # carefully unindex the object with integer id 'documentId'
    if not self._unindex.has_key(documentId):
        #logger.error( '% Attempt to unindex nonexistent document with id %s' % ( self.__class__.__name__, documentId ) )
        return

    path = self._unindex[documentId]
    comps = path.split('/')

    for level in range(len(comps[1:])):
        comp = comps[level+1]
        try:
            self._index[comp][level].remove(documentId)

            if len(self._index[comp][level])==0:
                del self._index[comp][level]
            if len(self._index[comp])==0:
                del self._index[comp]
        except KeyError:
            #logger.error( '% Attempt to unindex document with id %s failed' % ( self.__class__.__name__, documentId ) )
            pass

    try:
        del self._unindex[documentId]
    except KeyError:
        #logger.error( 'Patches.KeywordIndex Attempt to unindex nonexistent document id %s' % documentId )
        pass

PathIndex.unindex_object = pathindex_unindex_object

def unindex_removeForwardIndexEntry( self, entry, documentId ):
    # Take the entry provided and remove any reference to documentId
    # in its entry in the index.
    indexRow = self._index.get(entry, unindex_marker)
    if indexRow is not unindex_marker:
        try:
            indexRow.remove(documentId)
            if not indexRow:
                del self._index[entry]
                try: self.__len__.change(-1)
                except AttributeError: pass

        except AttributeError:
            # index row is an int
            del self._index[entry]
            try: self.__len__.change(-1)
            except AttributeError: pass

        except:
            #logger.error( '%s UnIndex_object could not remove documentId %s from index %s. This should not happen.' % ( \
            #    self.__class__.__name__, str(documentId), str(self.id) ), exc_info=True )
            pass
    else:
        logger.error( '%s UnIndex_object tried to retrieve set %s from index %s but couldn\'t. This should not happen.' % ( \
             self.__class__.__name__, repr(entry), str(self.id) ) )

UnIndex.removeForwardIndexEntry = unindex_removeForwardIndexEntry
"""

# ================================================================================================================
#   CRITICAL BUG's PATCHES (!)
# ================================================================================================================
#   Supersedes the Owned.changeOwnership method due to the accidental acquisition of the 'objectValues' method 
#   from parent containers which led to weird and unpredictable results.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching BUG: Owned.changeOwnership' )

from AccessControl.Owned import Owned, UnownableOwner, ownerInfo

def owned_changeOwnership( self, user, recursive=0, aq_get=aq_get ):
    new = ownerInfo(user)
    if new is None: return # Special user!
    owner = aq_get(self, '_owner', None, 1)

    if not recursive and ( owner == new or owner is UnownableOwner ):
        IsChangeOwner = 0
    else:
        IsChangeOwner = 1

    if hasattr( aq_base(self), 'objectValues' ):
        for child in self.objectValues():
            if recursive:
                child.changeOwnership(user, 1)
            else:
                # make ownership explicit
                child._owner = new

    if IsChangeOwner and owner is not UnownableOwner:
        self._owner = new

    if not getattr(self, 'creators', None):
        self.creators = tuplize('creators', new[1])

    logger.info('Patches.owned_changeOwnership user: %s, recursive: %s, owner %s, new %s of %s' % ( \
        `user`, recursive, owner, new, `self` ))

    try:
        if hasattr(self, 'reindexObject'):
            self.reindexObject( idxs=['Creator', 'allowedRolesAndUsers',] )
    except: pass

Owned.changeOwnership = owned_changeOwnership

# ----------------------------------------------------------------------------------------------------------------
#   Tweak access permissions on mxDateTime objects so that they can be used from restricted code.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching BUG: mxDateTime' )

from mx.DateTime import DateTimeType, RelativeDateTime
from AccessControl.SimpleObjectPolicies import ContainerAssertions

ContainerAssertions[ DateTimeType ] = 1
RelativeDateTime.__allow_access_to_unprotected_subobjects__ = 1

# ----------------------------------------------------------------------------------------------------------------
#   1. Provides HTTPRequest with a hacked variant of cgi.escape function to prevent errors during request 
#      stringification (non-string keys in request or response data container are the cause).
#
#   2. Adds 'setdefault' method for the record object.
#
#   3. Zope 2.6.1 memory leak patch: 
#      Fixed two leaks involving file uploads.  The HTTP input stream was referenced for too long.
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching BUG: HTTPRequest' )

from ZPublisher import HTTPRequest
from ZPublisher.BaseRequest import BaseRequest

def HTTPRequest_escape( s, quote=None ):
    return escape( str(s), quote )

def record_setdefault( self, key, value ):
    return self.__dict__.setdefault( key, value )

HTTPRequest.escape = HTTPRequest_escape
HTTPRequest.record.setdefault = record_setdefault

def HTTPRequest_close(self):
    # Clear all references to the input stream, possibly removing tempfiles
    self.stdin = None
    self._file = None
    self.form.clear()
    # we want to clear the lazy dict here because BaseRequests don't have
    # one.  Without this, there's the possibility of memory leaking
    # after every request.
    self._lazies = {}
    BaseRequest.close(self)

HTTPRequest.close = HTTPRequest_close

# ----------------------------------------------------------------------------------------------------------------
#   Replace Localizes`s patch for Publish, because it deletes reference to REQUEST uncorrectly
# ----------------------------------------------------------------------------------------------------------------

from ZPublisher import Publish

def _app_new_publish( request, *args, **kwargs ):
    #
    # Zope Publisher
    #
    thread_id = get_ident()
    if hasattr(Publish, '_requests'):
        Publish._requests[thread_id] = request
    try:
        x = Publish.old_publish(request, *args, **kwargs)
    finally:
        # in the conflict situation 'publish' method called again, recursively.
        # so reference deleted from innermost call, and we need this check.
        if hasattr(Publish, '_requests') and Publish._requests.has_key(thread_id):
            del Publish._requests[thread_id]
    return x

# add attr to function to easy validate that it is patched.
_app_new_publish._old = True

if hasattr(Publish, 'old_publish') and not hasattr(Publish.publish, '_old'):
    logger.info( 'Patching BUG: ZPublisher.Publish' )
    Publish.publish = _app_new_publish


# ================================================================================================================
#   ZPublisher SQL CONNECTOR
# ================================================================================================================

logger.info( 'ZPublisher.Publish Setup ZMySQLDA Connection' )

from Products.ZMySQLDA.db import DB

SQLDBs = {}
connection_string = ''
container = None

def setupProduct( DB, s, c ):
    global SQLDBs
    global connection_string
    global container

    thread_id = get_ident()

    SQLDBs[thread_id] = DB
    connection_string = s
    container = c

def getSqlConnection( s=None, check=None, item=None, object=None ):
    #
    # Returns SQLDB connection instance for current thread
    #
    global SQLDBs
    global connection_string
    global container

    thread_id = get_ident()

    if check:
        return ( SQLDBs, connection_string, container, )
    #if item:
    #    if item == 'connection_string':
    #        return connection_string
    #    elif item == 'container':
    #        return container
    #    elif SQLDBs.has_key(item):
    #        return SQLDBs[item]
    #    else:
    #        return None

    if not SQLDBs.has_key(thread_id) or SQLDBs[thread_id] is None:
        if object is not None:
            _before_publish_hook( None, object )
            return getSqlConnection()
        else:
            LOG('ZPublisher.publish %s' % thread_id, ERROR, 'no connection, SQLDBs: %s' % str(SQLDBs) )
            return None

    conn = SQLDBs[thread_id]

    if not conn.is_opened():
        conn.open( s or connection_string )
    return conn

def _before_publish_hook( path, ob ):
    #
    # Creates new SQLDB connection
    #
    global SQLDBs
    global connection_string
    global container

    thread_id = get_ident()

    if ob is None:
        if Config.IsPortalDebug:
            LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'before (no object), path: %s' % ( \
                path or '...' ) )
        return
    elif not getattr(ob, 'meta_type', None):
        if Config.IsPortalDebug:
            LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'before (no object), path: %s, meta_type: %s' % ( \
                path or '...', getattr(ob, 'meta_type', None) ) )
        return
    elif type(ob) is MethodType:
        object = ob.im_self
    else:
        object = ob

    try:
        #container = getToolByName(object, 'portal_url').getPortalObject()
        container = object.getPortalObject()
    except:
        pass

    if container is None:
        if Config.IsPortalDebug:
            LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'before (no container), path: %s' % ( \
                path or '...' ) )
        return
    elif not connection_string or Config.MultiSQLDBConnection:
        instance = userid = _x = None
        try:
            instance = aq_get(container, 'instance', None, 1) # object(!)
            acl_users = container.parent().acl_users
            user = acl_users.getUserById( Config.SQLDBUser )
            userid, _x = ( user.getUserName(), user.__ )
        except:
            LOG('ZPublisher.publish %s' % thread_id, ERROR, 'no instance [%s-%s-%s], container: %s' % ( \
                instance, userid, _x, `container` ) )
            raise
        connection_string = Config.connection_string % { \
            'instance' : instance,
            'user'     : userid,
            'passwd'   : _x
            }

    conn = DB( container=container )

    if conn is not None:
        SQLDBs[thread_id] = conn
        del conn
    else:
        if Config.IsPortalDebug:
            LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'before (no connection), path: %s' % ( \
                path or '...' ) )
        return

    if Config.IsPortalDebug:
        LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'before, path: %s, container: %s' % ( \
            path or '...', `container` ) )

def _after_publish_hook( abort=None ):
    #
    # Removes SQLDB connection for current thread
    #
    global SQLDBs
    global container

    thread_id = get_ident()

    if not SQLDBs.has_key(thread_id) or SQLDBs[thread_id] is None:
        return

    conn = SQLDBs[thread_id]
    if not conn.is_opened():
        conn.close()

    if abort is not None:
        AbortThread( container )
    else:
        SQLDBs[thread_id] = conn

    del SQLDBs[thread_id]
    del conn

    if Config.IsPortalDebug:
        LOG('ZPublisher.publish %s' % thread_id, DEBUG, 'after%s' % ( \
            abort and '(aborted)' or '' ))

def _error_publish_hook():
    #
    # Abort active thread
    #
    Publish.after_publish_hook( abort=1 )

Publish.setupProduct = setupProduct
Publish.getSqlConnection = getSqlConnection
Publish.after_publish_hook = _after_publish_hook
Publish.before_publish_hook = _before_publish_hook
Publish.error_publish_hook = _error_publish_hook


# ================================================================================================================
#   PersistenceMapping and Transience Classes PATCHES
# ================================================================================================================
#   ERROR:
#   TypeError: keys() takes exactly 1 argument (3 given)
#   Module Products.Transience.Transience, line 583, in _do_finalize_work
#   Override 'keys' method to implement 'begin' and 'end' key indexes for 'PersistentMapping' type(!)
# ----------------------------------------------------------------------------------------------------------------

logger.info( 'Patching PersistentMapping' )

from Globals import PersistentMapping

def mapping_p_resolveConflict( self, o, s, n ):
    #
    # Try to resolve conflict between container's objects
    #
    #logger.info( '!!! Patching PersistentMapping resolved new state !!!' )
    return n

PersistentMapping._p_resolveConflict = mapping_p_resolveConflict
"""
logger.info( 'Patching Transience' )

from Products.Transience import Transience

TRANSIENCE_BUCKET_CLASS = PersistentMapping # constructor for buckets
TRANSIENCE_DATA_CLASS = PersistentMapping # const for main data structure (timeslice->"bucket")

Transience.BUCKET_CLASS = TRANSIENCE_BUCKET_CLASS
Transience.DATA_CLASS = TRANSIENCE_DATA_CLASS
"""

# ================================================================================================================
#   ZODB ConflictResolution PATCHES
# ================================================================================================================

logger.info( 'Patching ConflictResolution' )

from ZODB.ConflictResolution import ConflictResolvingStorage, PersistentReferenceFactory, BadClassName, \
     state, find_global, persistent_id as resolution_persistent_id, \
     _unresolvable
from ZODB.utils import p64, u64, oid_repr

def transaction_tryToResolveConflict( self, oid, committedSerial, oldSerial, newpickle, committedData='', \
                                      source=None, check=None ):
    #
    # Try to resolve conflict. Implemented in some cases with *check* argument
    #
    class_info = ''
    storage = getattr(self,  '__name__', '')
    info = '\nthread  : %s' % get_ident()
    IsDebug = 1

    try:
        prfactory = PersistentReferenceFactory()
        file = StringIO(newpickle)
        unpickler = Unpickler(file)
        unpickler.find_global = find_global
        unpickler.persistent_load = prfactory.persistent_load
        meta = unpickler.load()
        class_info = str(meta)

        if isinstance(meta, tuple):
            klass = meta[0]
            newargs = meta[1] or ()
            if isinstance(klass, tuple):
                klass = find_global(*klass)
        else:
            klass = meta
            newargs = ()

        if klass in _unresolvable:
            logger.info("class is _unresolvable, class: %s" % klass.__name__)
            return check and (-1, 'bad class %s' % class_info) or None
        if klass is None:
            return check and (-2, 'class is None %s' % class_info) or None

        info += '\nstorage : %s' % storage
        info += '\noid     : %s' % oid_repr(oid)
        info += '\nclass   : %s' % getattr(klass, '__class__', '')
        info += '\nmodule  : %s' % getattr(klass, '__module__', '')

        #try: info += '\ndict:   %s' % str(klass.__dict__.keys())
        #except: pass

        newstate = unpickler.load()

        # -------------------------------------------------------------------------
        # For sessioning and another temporary storages we try to commit *newstate*
        # without executing of *_p_resolveConflict* action always
        # -------------------------------------------------------------------------

        if storage and storage.lower().startswith('temporary'):
            old = committed = None
            if newstate:
                resolved = newstate
                info += '\nforced  : newstate'
            else:
                raise ConflictError

        # --------------------------------
        # In any case, we resolve conflict
        # --------------------------------

        else:
            inst = klass.__new__(klass, *newargs)

            try:
                resolve = inst._p_resolveConflict
            except AttributeError:
                _unresolvable[klass] = 1
                logger.info("has not _p_resolveConflict, class: %s" % klass.__name__)
                return check and (-3, 'resolve is missing %s' % class_info) or None

            old = state(self, oid, oldSerial, prfactory)
            committed = state(self, oid, committedSerial, prfactory, committedData)

            try: info += '\nid      : %s' % str(committed['id'])
            except: pass
            try: info += '\nnd_uid  : %s' % str(committed['nd_uid'])
            except: pass

            resolved = resolve(old, committed, newstate)

        # --------------------------------------------------------------
        # And even more..., we can ignore conflict by some reason at all
        # --------------------------------------------------------------

            if type(resolved) == type(1):
                IsDebug = resolved and 1 or 0
                resolved = committed
                info += '\nforced  : committed'

        file = StringIO()
        pickler = Pickler(file,1)
        pickler.persistent_id = resolution_persistent_id
        pickler.dump(meta)
        pickler.dump(resolved)

        if IsDebug and ( class_info or info ) and Config.IsPortalDebug:
            LOG('Conflict Resolution', DEBUG, 'resolved: %s%s' % ( class_info, info ))
        return file.getvalue(1)

    except ( ConflictError, BadClassName ):
        if class_info or info:
            LOG('Conflict Resolution', DEBUG, '(!) unresolved: %s%s' % ( class_info, info ))
        return check and (0, class_info) or None
    except:
        # If anything else went wrong, catch it here and avoid passing an
        # arbitrary exception back to the client.  The error here will mask
        # the original ConflictError.  A client can recover from a
        # ConflictError, but not necessarily from other errors.  But log
        # the error so that any problems can be fixed.
        logger.error("Unexpected error", exc_info=True)
        return None

if not hasattr( ConflictResolvingStorage, 'transaction_tryToResolveConflict' ):
    ConflictResolvingStorage._transaction_tryToResolveConflict = ConflictResolvingStorage.tryToResolveConflict

ConflictResolvingStorage.tryToResolveConflict = transaction_tryToResolveConflict


# ================================================================================================================
#   ZODB ExportImport PATCHES
# ================================================================================================================

from Config import AppClasses
from ZODB.ExportImport import ExportImport, Ghost, persistent_id, export_end_marker
from ZODB.POSException import ExportError
from cStringIO import StringIO
from cPickle import Pickler, Unpickler

logger.info( 'Patching ZODB ExportImport.ExportFile' )

from ZODB.serialize import referencesf
from tempfile import TemporaryFile

interrupt_threshold = 50

def ExportFile( self, oid, f=None ):
    #
    # Export .zexp file. 
    # Implemented threading interrupts
    #
    if f is None:
        f = TemporaryFile()
    elif isinstance(f, str):
        f = open(f,'w+b')

    logger.info("exported file:\n%s" % f)

    f.write('ZEXP')
    oids = [oid]
    done_oids = []
    done = done_oids.append
    load = self._storage.load
    n = 0 
    i = 0

    while oids:
        oid = oids.pop(0)
        if oid in done_oids:
            continue
        done(oid)
        i += 1
        try:
            p, serial = load(oid, self._version)
        except:
            logger.debug("broken reference for oid %s", repr(oid), exc_info=True)
        else:
            referencesf(p, oids)
            #logger.info("oids: %s" % oids)
            f.writelines([oid, p64(len(p)), p])
            #logger.info("exported oid: %s\np: %s" % (repr(oid), p))

        if i == interrupt_threshold:
            threading.Event().wait( 0.1 )
            i = 0
        n += 1

    f.write(export_end_marker)

    logger.info('total exported %s objects' % n)
    return f

ExportImport.exportFile = ExportFile

logger.info( 'Patching ZODB ExportImport.ImportDuringCommit' )

def ImportDuringCommit( self, transaction, f, return_oid_list ):
    #
    # Import data during two-phase commit.
    # Invoked by the transaction manager mid commit.
    # Appends one item, the OID of the first object created, to return_oid_list.
    #
    oids = {}
    n = 0

    logger.info("imported file:\n%s" % f)

    def persistent_load( ooid ):
        # Remap a persistent id to a new ID and create a ghost for it.
        #logger.info("ooid: %s" % str(ooid))
        klass = None
        if isinstance(ooid, tuple):
            ooid, klass = ooid
        if ooid in oids:
            oid = oids[ooid]
        else:
            if klass is None:
                oid = self._storage.new_oid()
            else:
                oid = self._storage.new_oid(), FixClass( klass )
            oids[ooid] = oid
        #logger.info("oid: %s" % str(oid))
        return Ghost(oid)

    version = self._version
    i = 0

    while 1:
        h = f.read(16)
        if h == export_end_marker:
            break
        if len(h) != 16:
            raise ExportError("Truncated export file")
        l = u64(h[8:16])
        p = f.read(l)
        if len(p) != l:
            raise ExportError("Truncated export file")

        ooid = h[:8]
        if oids:
            oid = oids[ooid]
            if isinstance(oid, tuple):
                oid = oid[0]
        else:
            oids[ooid] = oid = self._storage.new_oid()
            return_oid_list.append(oid)

        pfile = StringIO(p)
        unpickler = Unpickler(pfile)
        unpickler.persistent_load = persistent_load

        meta = ob = upgraded = None
        i += 1

        try:
            meta = unpickler.load()
            ob = unpickler.load()
        except:
            #logger.error("error unpickler, oid: %s, meta: %s\nob: %s\noids: %s\np: %s" % ( oid_repr(oid), meta, str(ob), oids, p))
            LOG('Patches.ImportDuringCommit', DEBUG, "error unpickler, oid: %s, meta: %s\nob: %s\noids: %s\np: %s" % ( \
                oid_repr(oid), meta, str(ob), oids, p))
            raise

        meta, upgraded = CleanAndUpgradeClass( meta, ob, oid )

        newp = StringIO()
        pickler = Pickler(newp, 1)
        pickler.persistent_id = persistent_id

        try:
            pickler.dump(meta)
            pickler.dump(upgraded)
        except:
            #logger.error("error pickler, oid: %s, meta: %s\nob: %s\noids: %s\np: %s" % ( oid_repr(oid), meta, str(ob), oids, p))
            LOG('Patches.ImportDuringCommit', DEBUG, "error pickler, oid: %s, meta: %s\nob: %s\noids: %s\np: %s" % ( \
                oid_repr(oid), meta, str(ob), oids, p))
            raise

        p = newp.getvalue()
        self._storage.store(oid, None, p, version, transaction)

        if i == interrupt_threshold:
            threading.Event().wait( 0.1 )
            i = 0
        n += 1

    logger.info('total imported %s objects' % n)

def FixClass( klass ):
    if isinstance(klass, tuple):
        m, k = klass
        if m.startswith('Products'):
            m = m.replace('Common', 'ExpressSuite')
        return (m, k)
    return klass

def CleanAndUpgradeClass( meta, ob, oid ):
    #
    # Clean and upgrade class of object
    #
    IsUpgraded = IsMissing = IsCleaned = 0
    klass = None

    try: uid = ob.get('nd_uid')
    except: uid = None

    if meta and isinstance(meta, tuple):
        new = []
        for n in range(len(meta)):
            x = meta[n]
            if n == 0 and isinstance(x, tuple):
                m, c = FixClass(x)
                if m not in x:
                    IsUpgraded = 1
                new.append( ( m, c ) )
                klass = c
            else:
                new.append( x )
        meta = tuple(new)
        del new

    if ob is not None and type(ob) is DictType and klass is not None:
        for x in ('_container',):
            if ob.has_key(x) and type(ob[x]) is DictType:
                for key, value in ob[x].items():
                    if type(value) is type(Missing):
                        ob[x][key] = MissingValue
                        IsMissing = 1

        if klass in ('ContentVersion',):
            for x in ('cooked_text', 'text',):
                s = ''
                if ob.has_key(x):
                    s = re.sub(r'naudoc\:', 'express:', ob[x])
                    ob[x] = s
                    IsCleaned = 1
                del s
            if ob['cooked_text'] == ob['text']:
                ob['cooked_text'] = ''
                IsCleaned = 1

    if IsUpgraded:
        #logger.info("Upgraded object uid:%s, meta: %s" % ( uid, meta ))
        LOG('Patches.CleanAndUpgradeClass', DEBUG, "Upgraded object uid:%s, meta: %s" % ( uid, meta ))

    if IsMissing:
        #logger.info("Missing uid:%s, oid:%s, meta: %s\nattrs: %s" % ( uid, oid_repr(oid), meta, ob ))
        LOG('Patches.CleanAndUpgradeClass', DEBUG, "Missing uid:%s, oid:%s, meta: %s\nattrs: %s" % ( uid, oid_repr(oid), meta, ob ))

    if IsCleaned:
        #logger.info("Cleaned object uid:%s, klass: %s" % ( uid, klass ))
        LOG('Patches.CleanAndUpgradeClass', DEBUG, "Cleaned object uid:%s, klass: %s" % ( uid, klass ))

    #if klass in ( 'ContentVersion', 'HTMLDocument', 'TaskItem', ):
    #    logger.info("meta: %s, attrs: %s" % ( meta, ob ))

    return ( meta, ob )

ExportImport._importDuringCommit = ImportDuringCommit


# ================================================================================================================
#   ZODB Commit PATCHES
# ================================================================================================================
#   Saves objects modified by their _initstate method during autoupdate.
#   The reason to have this is that it is impossible to set _p_changed flag inside __setstate__.
# ----------------------------------------------------------------------------------------------------------------

def connection_commit( self, transaction ):
    thread_id = get_ident()

    #logger.info( 'in Connection._commit hook' )
    LOG('TID.%s: Patches.connection_commit' % thread_id, DEBUG, 'in Connection._commit hook' )

    for ob in self._registered_objects:
        if Config.AutoUpdateObjects:
            if getattr( ob, '_Persistent__changed', None ):
                del ob._Persistent__changed
                if not ob._p_changed:
                    ob._p_changed = 1

                try: ob_repr = repr(ob)
                except: ob_repr = '<%s instance at 0x%x>' % ( ob.__class__.__name__, id(ob) )
                try: ob_id = ob.getId()
                except: ob_id = getattr( ob, '__name__', '<unknown>' )

                #logger.info( 'Connection._commit: updated %s [%s]' % ( ob_repr, ob_id ))
                #LOG('Patches.connection_commit', DEBUG, 'updated %s [%s]' % ( ob_repr, ob_id ))

    self._connection_commit( transaction )

if Config.AutoUpdateObjects or not Config.DisablePersistentActionsLog:
    logger.info( 'Patching ZODB Connection' )
    from ZODB.Connection import Connection

    if not hasattr( Connection, '_connection_commit' ):
        Connection._connection_commit = Connection._commit

    Connection._commit = connection_commit


# ================================================================================================================
#   OTHER APP EXTENSIONS
# ================================================================================================================

logger.info( 'Patching CMFCore.RegistrationTool.generatePassword' )

from Products.CMFCore.RegistrationTool import RegistrationTool

def _express_generatePassword(self):
    #
    # Generates a password with a policy
    #
    import string, random
    res = []
    chars = ''.join([x.lower()+x.upper() for x in string.lowercase[:26]])
    for n in range(12):
        res.append(random.choice(chars))
    chars = '!#_-'
    for n in range(3):
        res.append(random.choice(chars))
    chars = string.digits
    for n in range(8):
        res.append(random.choice(chars))
    passwd = ''
    for n in range(8):
        passwd += random.choice(res)
    return passwd

if not hasattr(RegistrationTool, '_old_generatePassword'):
    RegistrationTool._old_generatePassword = RegistrationTool.generatePassword

RegistrationTool.generatePassword = _express_generatePassword

# ================================================================================================================

logger.warning( 'Server has been refreshed or restarted' )
