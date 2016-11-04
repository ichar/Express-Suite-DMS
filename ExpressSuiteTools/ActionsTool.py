"""
Actions list tool
$Id: ActionsTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 06/07/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import DictType, InstanceType
from string import lower

from AccessControl import ClassSecurityInfo
from Acquisition import aq_inner, aq_parent, aq_base

from Products.CMFCore.ActionsTool import ActionsTool as _ActionsTool
from Products.CMFCore.ActionInformation import ActionInformation as _ActionInformation, oai as _oai
from Products.CMFCore.Expression import createExprContext as _createExprContext
from Products.CMFCore.utils import getToolByName, _checkPermission
from Products.CMFCore.TypesTool import TypeInformation
from zExceptions import Unauthorized

from SimpleObjects import ToolBase

from Utils import InitializeClass


default_allowed_types = ( \
    'ExpressSuiteCore', 'HTMLDocument', 'HTMLCard', 'Heading', 'Fax Incoming Folder', 'Shortcut', \
    'Link', 'Task Item', 'Registry', )

default_restricted_actions = ( \
    'configPortal', 'configBackupFSRoot', 'manage', 'manageComments', 'addUser', 'join', ) #,'manageCategories', 'undo'

default_disabled_in_archive_actions = ( \
    'register', 'link', 'request_confirmation', 'ownership', )

default_sort_order = { \
    'Log out' : 0,
    'Manage groups' : 1,
    'Manage users' : 2,
    'Create user' : 3,
    'Personal properties' : 4,
    'Interface preferences' : 5,
    'Change password' : 6,

    'Undo' : 0,
    'Document categories' : 1,
    'Manage resolutions' : 2,
    'Configure pack and backup options' : 3,
    'Manage scheduler' : 4,
    'Manage portal archive' : 5,
    'Reconfigure Portal' : 6,
    'Sync portal tools' : 7,
}


class ActionsTool( ToolBase, _ActionsTool ):
    """
        Portal actions tool
    """
    _class_version = 1.0

    meta_type = 'ExpressSuite Actions Tool'

    security = ClassSecurityInfo()

    manage_options = _ActionsTool.manage_options # + ToolBase.manage_options

    def IsPortalAvailable( self ):
        """
            Checks the site availability
        """
        membership = getToolByName( self, 'portal_membership', None )
        try:
            member = membership.getAuthenticatedMember()
            IsManager = member.IsManager()
            IsAdmin = member.IsAdmin()
        except:
            IsManager = IsAdmin = 0

        prptool = getToolByName( self, 'portal_properties', None )
        if prptool is not None and prptool.getProperty( 'emergency_service' ) and not IsAdmin:
            return 0
        else:
            return 1

    security.declarePublic('listWorkflowActionsFor')
    def listWorkflowActionsFor( self, object, url=None ):
        """
            Returns workflow actions for a task item based inside the document
        """
        if object is None or getattr(object, 'meta_type', None) != 'Task Item':
            return []
        actions = self.listFilteredActionsFor( object.getBase() ) # , object.relative_url(frame='inFrame')
        actions = actions and actions.get('workflow') or []
        if url:
            ob_url = 'followup/%s/%s' % ( object.getId(), url )
            for x in actions:
                x['url'] = x['url'].replace('change_state', ob_url)
        return actions

    security.declarePublic('listFilteredActionsFor')
    def listFilteredActionsFor( self, object=None, object_url=None, no_clean=None ):
        """
            Gets all actions available to the user and returns a mapping containing user actions,
            object actions, and global actions.
        """
        msg = getToolByName( self, 'msg', None )
        membership = getToolByName( self, 'portal_membership', None )
        metadata = getToolByName( self, 'portal_metadata', None )
        tptypes = getToolByName( self, 'portal_types', None )
        if None in ( membership, tptypes, metadata, msg ):
            return None

        portal = aq_parent(aq_inner(self))
        user = membership.getAuthenticatedMember()
        IsManager = user.IsManager()
        IsAdmin = user.IsAdmin()

        if object is None or not hasattr( object, 'aq_base' ):
            folder = portal
        else:
            folder = object
            # Search up the containment hierarchy until we find an
            # object that claims it's a folder.
            while folder is not None:
                if getattr(aq_base(folder), 'isPrincipiaFolderish', 0):
                    # found it.
                    break
                else:
                    folder = aq_parent(aq_inner(folder))

        if object_url is None:
            object_url = object is not None and object.absolute_url() or ''

        meta_type = object is None and 'None' or getattr( object, 'meta_type', None )

        if object_url == 'inFrame?link=.' and not IsAdmin and meta_type not in default_allowed_types:
            #raise Unauthorized, "You are not allowed to access this resource: %s " % object_url
            return None

        ec = createExprContext( folder, portal, object, url=object_url )
        actions = []

        # Include actions from specific tools
        for provider_name in self.listActionProviders():
            provider = getattr( self, provider_name )
            #self._listActions( append, provider, info, ec )
            actions.extend( self._listActionInfos( provider, object ) )

        # Include actions from object
        if object is not None and tptypes is not None:
            base = aq_base(object)
            # we might get None back from getTypeInfo.  We construct a dummy TypeInformation object 
            # here in that case (the 'or' case).
            # this prevents us from needing to check the condition.
            ti = tptypes.getTypeInfo( object ) or TypeInformation('Dummy')
            defs = ti.listActions()
            url = object_url

            for d in defs:
                condition = getattr(d, 'condition', None)
                if condition and not condition(ec):
                    continue

                x = {}
                x['id'] = getattr(d, 'id', None)
                x['permissions'] = getattr(d, 'permissions', None)
                x['name'] = getattr(d, 'title', None)
                if hasattr(d, 'action'):
                    x['action'] = getattr(d, 'action', None)
                    url = '%s/%s' % ( object_url or '', x['action'](ec) )
                x['url'] = url
                x['category'] = getattr(d, 'category', 'object')
                x['visible'] = getattr(d, 'visible', 1)

                if object.archive() and x['id'] in default_disabled_in_archive_actions:
                    continue
                #if x['id'] == 'edit': 
                #    if object.implements('isLockable') and object.isLocked() or \
                #        workflow.getInfoFor( object.aq_parent, 'state', '' ) != 'editable' or \
                #        object.IsSystemObject():
                #        continue
                if x['id'].find('reply_to_document') > -1:
                    if not object.implements('isHTMLDocument'):
                        continue
                    category_id = object.Category()
                    category = metadata.getCategoryById( category_id )
                    if category is None:
                        continue
                    if not category.getReplyToAction():
                        continue
                    home = user.getPersonalFolderUrl()
                    if not home:
                        continue
                    x['url'] = '%s/reply_to_document?category=%s&uid=%s' % ( home, category_id, object.getUid() )

                actions.append( x )

            if hasattr( base, 'listActions' ):
                #self._listActions( append, object, info, ec )
                #actions.extend( self._listActionInfos( object, object ) )
                pass

        # Reorganize the actions by category, filtering out disallowed actions
        filtered_actions = { 'user' : [], 'folder' : [], 'object' : [], 'global' : [], 'workflow' : [], }

        for action in actions:
            if not IsAdmin and ( not action.has_key('id') or action['id'] in default_restricted_actions ):
                continue
            category = action['category']
            permissions = action.get('permissions', None)
            visible = action.get('visible', 1)
            if not visible:
                continue

            action['sort_order'] = default_sort_order.get(action['name'], 0)
            verified = 0

            if not permissions:
                # This action requires no extra permissions.
                verified = 1
            else:
                if object is not None and ( category.startswith('object') or category.startswith('workflow') ):
                    context = object
                elif folder is not None and category.startswith('folder'):
                    context = folder
                else:
                    context = portal
                for permission in permissions:
                    # The user must be able to match at least one of the listed permissions.
                    if _checkPermission( permission, context ):
                        verified = 1
                        break

            if verified:
                catlist = filtered_actions.get( category, None )
                if catlist is None:
                    filtered_actions[category] = catlist = []
                # Filter out duplicate actions by identity...
                if not action in catlist:
                    catlist.append(action)
                # ...should you need it? 
                # here's some code that filters by equality (use instead of the two lines above)
                #if not [a for a in catlist if a==action]:
                #    catlist.append(action)

        if not no_clean:
            for key in filtered_actions.keys():
                action = filtered_actions[key]
                for x in action:
                    try:
                        url = x['url']
                        n = url.find('transition=')
                        if n > 0:
                            x['action'] = url[n+11:]
                    except:
                        x['action'] = None
                    x['name'] = msg( x['name'], add=0 )

        return filtered_actions

    # listFilteredActions() is an alias.
    security.declarePublic( 'listFilteredActions' )
    listFilteredActions = listFilteredActionsFor

    security.declarePublic( 'getAction' )
    def getAction( self, id ):
        object = aq_parent( self )
        folder = object.parent()
        info = oai( self, folder, object )
        ec = createExprContext( folder, self.parent(), object )
        action = None

        if hasattr( aq_base(object), 'listActions' ):
            action = self._getAction( id, object, info, ec )

        if action is None:
            for name in self.listActionProviders():
                provider = getToolByName( self, name )
                action = self._getAction( id, provider, info, ec )
                if action is not None:
                    break

        if action is not None:
            action['url'] = action['url'].strip()
            if action.has_key('name'):
                msg = getToolByName( self, 'msg' )
                action['name'] = msg( action['name'], add=0 )
            return action

        return None

    security.declarePublic( 'getActionIcon' )
    def getActionIcon( self, id ):
        action = self.getAction( id )
        if action is None:
            return ''
        action.setdefault( 'icon', 'help.gif' )
        return _action_icon_link % action

    def _getAction( self, id, provider, info, ec ):
        actions = provider.listActions( info )
        if not actions:
            return None

        for action in actions:
            if type(action) is DictType:
                if action.has_key('id') and action['id'] == id:
                    return action.copy()

            elif action.getId() == id:
                if not action.testCondition( ec ):
                    return None
                return action.getAction( ec )

        return None

InitializeClass( ActionsTool )


_action_icon_link = """
<a href="%(url)s" title="%(name)s" class="action_icon">
        <img src="%(icon)s" alt="%(name)s" /></a>
"""

class ActionInformation( _ActionInformation ):
    """
        Represents a single selectable action.
        See CMF Core documentation.
    """
    def __init__( self, icon=None, **kw ):
        _ActionInformation.__init__( self, **kw )
        self.icon = icon

    def getAction( self, ec ):
        info = _ActionInformation.getAction( self, ec )
        info['icon'] = self.icon
        return info


def createExprContext( folder, portal, object, url=None ):
    context = _createExprContext( folder, portal, object )
    vars = context.global_vars

    if url is not None:
        vars['object_url'] = url

    elif object is not None:
        try: vars['object_url'] = object.relative_url()
        except AttributeError: pass

    return context


class oai( _oai ):

    def __init__( self, tool, folder, object=None, url=None ):
        _oai.__init__( self, tool, folder, object )

        if url is not None:
            self.content_url = url
        elif object is not None:
            try:
                self.content_url = object.relative_url()
            except AttributeError: 
                pass
