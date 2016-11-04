"""
WorkflowTool class
$Id: WorkflowTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys, traceback
from types import StringType, DictType, TupleType
from copy import deepcopy

import ThreadLock

from Acquisition import Implicit, aq_parent, aq_base, aq_inner
from AccessControl import ClassSecurityInfo
from OFS.Folder import Folder
from UserDict import UserDict
from MethodObject import Method

from Globals import PersistentMapping
from ZODB.POSException import ConflictError, ReadConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.WorkflowCore import WorkflowException, ObjectDeleted, ObjectMoved
from Products.CMFCore.WorkflowTool import WorkflowTool as _WorkflowTool, addWorkflowFactory, _marker as workflow_marker
from Products.CMFCore.utils import getToolByName, _checkPermission

from Products.DCWorkflow.DCWorkflow import DCWorkflowDefinition
from Products.DCWorkflow.Expression import Expression
from Products.DCWorkflow.ContainerTab import ContainerTab as _ContainerTab
from Products.DCWorkflow.Scripts import Scripts as _Scripts
from Products.DCWorkflow.States import States as _States, StateDefinition
from Products.DCWorkflow.Transitions import Transitions as _Transitions, TransitionDefinition
from Products.DCWorkflow.Variables import Variables
from Products.DCWorkflow.Worklists import Worklists
from Products.DCWorkflow.utils import modifyRolesForPermission

from Exceptions import ResourceLockedError, Unauthorized, SimpleError
from SimpleObjects import Persistent, ToolBase, InstanceBase, ExpressionWrapper
from PortalLogger import portal_log, portal_error, print_traceback

from Utils import InitializeClass, UnrestrictedCheckObject, getClientStorageType, getRelativeURL

from logging import getLogger
logger = getLogger( 'WorkflowTool' )


class WorkflowTool( ToolBase, _WorkflowTool ):
    """
        This tool accesses and changes the workflow state of content
    """
    _class_version = 1.01

    id = 'portal_workflow'
    meta_type = 'ExpressSuite Workflow Tool'

    security = ClassSecurityInfo()

    manage_options = _WorkflowTool.manage_options # + ToolBase.manage_options

    _chains_by_type = None
    _default_chain = ('default_workflow',)

    # restore WorkflowTool methods overridden by ToolBase
    listActions = _WorkflowTool.listActions

    lock = ThreadLock.allocate_lock()

    def _initstate( self, mode ):
        """ 
            Initializes attributes
        """
        if not ToolBase._initstate(self, mode):
            return 0

        if self._chains_by_type is not None and type(self._chains_by_type) != type({}):
            try:
                items = self._chains_by_type.items()
            except:
                items = []
            container = {}
            for key, value in items:
                container[ key ] = value
            self._chains_by_type = container
            self._p_changed = 1

            logger.info('initstate _chains_by_type, keys: %s' % len(self._chains_by_type.keys()))

        return 1

    def setProperties( self, wf, title='dc_workflow', REQUEST=None ):
        """
            Sets the workflow properties.

            Arguments:

                'wf' -- Workflow id string.

                'title' -- New workflow title.
        """
        workflow = self[wf]
        workflow.setProperties( title=title )
        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/workflow_properties?wf=' + wf + \
                    '&portal_status_message=Properties+changed' )

    def getSortedStateList( self, wf, ret_type=None ):
        """
            Returns sorted workflow states list.

            Arguments:

                'wf' -- Workflow id string.
        """
        if wf:
            workflow = self[wf]
        else:
            return None
        
        states = workflow.states
        if not states:
            return None
        
        msg = getToolByName( self, 'msg' )
        archive = getClientStorageType( self )

        if archive:
            states_list = [ ( msg( x.title ), x.getId() ) for x in states.values() if x.getId() in ['OnArchive','OnStorage'] ]
        else:
            states_list = [ ( msg( x.title ), x.getId() ) for x in states.values() ]

        states_list.sort()

        if ret_type is None:
            results = []
            for title, id in states_list:
                results.append( id )
        else:
            results = {}
            for title, id in states_list:
                results[id] = workflow.states[id]
        
        return results

    def getSortedTransitionsList( self, wf, auto=None, ret_type=None ):
        """
            Returns sorted workflow transitions list.

            Arguments:

                'wf' -- Workflow id string.
        """
        if wf:
            workflow = self[wf]
        else:
            return None

        transitions = workflow.transitions
        if not transitions:
            return None

        msg = getToolByName( self, 'msg', None )
        transitions_list = []

        for transition in transitions.values():
            title = transition.title
            if title[0:1] == '_' or title[-1:] == '_':
                if auto == 0: continue
            else:
                if auto == 1: continue
            transitions_list.append( ( transition.title, transition.getId() ) )

        transitions_list.sort()

        if ret_type is None:
            results = []
            for title, id in transitions_list:
                results.append( id )
        else:
            results = {}
            for title, id in transitions_list:
                results[id] = workflow.transitions[id]

        return results

    def addState( self, wf, state_id, REQUEST=None ):
        """
            Adds new state to the specified workflow.

            Arguments:

                'wf' -- Workflow id string.

                'state_id' -- New state id string.
        """
        workflow = self[wf]
        workflow.states.addState(state_id)

        if REQUEST is None:
            return

        REQUEST['RESPONSE'].redirect( self.portal_url() + '/states?wf=' + wf + \
                '&portal_status_message=State+added' )

    def deleteStates( self, wf, ids, REQUEST=None ):
        """
            Deletes states from the specified workflow.

            Arguments:

                'wf' -- Workflow id string.

                'ids' -- List of state id strings.

        """
        workflow = self[wf]

        if ids:
            workflow.states.deleteStates(ids)
            transitions = workflow.transitions
            # fix transitions
            for transition in transitions.values():
                if transition.new_state_id in ids and transitions.isPrivateItem(transition):
                    id = transition.id
                    title = transition.title
                    actbox_name = transition.actbox_name
                    new_state_id = ''
                    self.setTransitionProperties(wf, id, title, actbox_name, new_state_id)

        if REQUEST is None:
            return

        REQUEST['RESPONSE'].redirect( self.portal_url() + '/states?wf=' + wf + \
                '&portal_status_message=State(s)+removed' )

    def setStateProperties( self, wf, state_id, title, transitions, disable_brains_type=None, REQUEST=None ):
        """
            Sets state properties.

            Arguments:

                'wf' -- Workflow id string.

                'state_id' -- State id string.

                'title' -- State title.

                'transitions' -- List of allowed transition ids.

            In case the specified state is acquired from the parent category, it
            should automatically become private before new state properties will
            be applied.
        """
        states = self[wf].states
        sdef = states[state_id]
        sdef = states.makePrivateItem(sdef)
        sdef.setProperties( title=title, transitions=transitions )

        setattr(sdef, 'disable_brains_type', disable_brains_type)

        if REQUEST is None:
            return

        REQUEST['RESPONSE'].redirect( self.portal_url() + '/state_properties?wf=' + wf + \
                '&state=' + state_id + '&portal_status_message=State+properties+changed' )

    def getStateDisableBrainsType( self, wf, state_id ):
        """
            Returns state's 'disable_brains_type' property
        """
        states = self[wf].states
        sdef = states[state_id]
        return sdef is not None and getattr(sdef, 'disable_brains_type', None)

    def setStatePermissions( self, wf, state_id, REQUEST=None, redirect=1, force_update_roles=1 ):
        """
            Sets state permissions.

            Arguments:

                'wf' -- Workflow id string.

                'state_id' -- State id string.

                'REQUEST' -- REQUEST object containing the form with new state
                             permissions settings represented as the combination
                             of '<permission>|<role>' and 'acquire_<permission>'
                             input fields.

                'redirect' -- Boolean value indicating whether the user should
                              be redirected to the state properties management
                              form or not.
        """
        states = self[wf].states
        sdef = states[state_id]
        sdef = states.makePrivateItem(sdef)
        sdef.setPermissions(REQUEST)

        if force_update_roles:
            self._updateRoleMappings( wf, state_id )

        if REQUEST is None:
            return

        if redirect:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/state_properties?wf=' + wf + \
                    '&state=' + state_id + '&portal_status_message=State+properties+changed' )

    def _updateRoleMappings( self, wf, state_id ):
        # Update role mappings and recursively reindex objects of the same
        # category and state.
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            return

        results = catalog.unrestrictedSearch( state=state_id, hasBase=self[wf].getCategoryDefinition().getId() )
        if not results:
            return

        for r in results:
            ob = r.getObject()
            if ob is None:
                continue
            wf = ob.getCategory().getWorkflow()
            if wf is not None and wf.updateRoleMappingsFor( ob ):
                catalog.reindexObject( ob, idxs=['allowedRolesAndUsers'], recursive=1 )

    def getStateTitle( self, wf, state_id ):
        """
            Returns the workflow state title.

            Arguments:

                'wf' -- Workflow id string.

                'state_id' -- State id string.

            Result:

                String.
        """
        try:
            workflow = self[wf]
            state = workflow.states.get(state_id)
            if state:
                title = state.title
                return (title or state_id)
        except:
            return state_id

        return

    def addTransition( self, wf, trans_id, REQUEST=None ):
        """
            Adds transition to the specified workflow.

            Arguments:

                'wf' -- Workflow id string.

                'trans_id' -- New transition id string.
        """
        workflow = self[wf]
        workflow.transitions.addTransition(trans_id)
        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/transitions?wf=' + wf + \
                    '&portal_status_message=Transition+added' )

    def deleteTransitions( self, wf, ids, REQUEST=None ):
        """
            Deletes transitions from the specified workflow.

            Arguments:

                'wf' -- Workflow id string.

                'ids' -- List of transition id strings.
        """
        workflow = self[wf]
        workflow.transitions.deleteTransitions(ids)

        # delete transition ids from states
        states = workflow.states
        for state in states.values():
            if states.isPrivateItem(state):
                transitions = state.getTransitions()
                for transition_id in ids:
                    if transition_id in transitions:
                        transitions.remove( transition_id )
                self.setStateProperties(wf, state.getId(), state.title, transitions)

        if REQUEST is not None:
            REQUEST['RESPONSE'].redirect( self.portal_url() + '/transitions?wf=' + wf + \
                    '&portal_status_message=Transition(s)+removed' )

    def setTransitionProperties( self, wf, transition, title, actbox_name, new_state_id, trigger_type=1 ):
        """
            Sets transition properties.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

                'title' -- Transition title.

                'actbox_name' -- Transition name to be used in the action box.

                'new_state_id' -- State id string. Specifies the transition destination state.

                'trigger_type' -- Specifies the way transition is invoked by the workflow.
                
            Currently DCWorkflow defines the following trigger types: TRIGGER_AUTOMATIC,
            TRIGGER_USER_ACTION and TRIGGER_WORKFLOW_METHOD.
        """
        transitions = self[wf].transitions
        tdef = transitions[transition]
        tdef = transitions.makePrivateItem(tdef)

        trigger_type = int(trigger_type)
        script_name =''
        after_script_name = ''
        actbox_url = '%(content_url)s/change_state?transition=' + transition

        tdef.setProperties( title, new_state_id, trigger_type, script_name, after_script_name, actbox_name, actbox_url )

    def getTransitionInfo( self, wf, transition ):
        """
            Returns transition properties.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

            Result:

            Mapping with the following keys: 'title', 'new_state_id', 'actbox_name',
            'actbox_url'.

        """
        workflow=self[wf]
        transition = workflow.transitions[transition]
        ti = { 'title': transition.title,
                 'new_state_id': transition.new_state_id,
                 'actbox_name': transition.actbox_name,
                 'actbox_url': transition.actbox_url,
             }
        return ti

    def getTransitionTitle( self, wf, transition ):
        """
        Returns the workflow transition title.

        Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

            Result:

              String.
        """
        try: return self[ wf ].transitions[ transition ].title
        except KeyError: return ''

    def getTransitionGuard( self, wf, transition ):
        """
            Returns the workflow transition guard.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

            Result:

                Guard class instance.
        """
        workflow = self[wf]
        tr = workflow.transitions[transition]
        guard = tr.getGuard()
        return guard

    def getTransitionGuardRoles( self, wf, transition ):
        """
            Lists the user roles required by the transition guard.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

            Note:

                This method should become obsolete soon.

            Result:

              List of guard roles.

        """
        guard = self.getTransitionGuard(wf, transition)
        return guard.roles

    def setTransitionGuardRoles( self, wf, transition, roles ):
        """
            Sets transition guard roles.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

                'roles' -- List of guard roles.

            Note:

                This method should become obsolete soon.
        """
        guard = self.getTransitionGuard(wf, transition)
        guard.roles = roles
        workflow = self[wf]
        workflow.transitions[transition].guard = guard

        return

    def getTransitionGuardRules( self, wf, transition ):
        """
            Lists the user rules required by the transition guard.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

            Note:

                This method should become obsolete soon.

            Result:

              List of guard rules.
        """
        guard = self.getTransitionGuard(wf, transition)
        try:
            if not guard.expr: return None
        except:
            return None
        return str(guard.expr.text)

    def setTransitionGuardRules( self, wf, transition, rules_expr ):
        """
            Sets the expression required by the transition guard.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

                'rules_expr' -- Rule expression.

            Note:

                This method should become obsolete soon.
        """
        guard = self.getTransitionGuard(wf, transition)
        guard.expr = Expression(text=rules_expr)
        workflow = self[wf]
        workflow.transitions[transition].guard = guard

        return

    def setTransitionGuardPermissions( self, wf, transition, permissions ):
        """
            Sets the permissions required by the transition guard.

            Arguments:

                'wf' -- Workflow id string.

                'transition' -- Transition id string.

                'permissions' -- List if required permissions.

            Note:

                This method should become obsolete soon.
        """
        guard = self.getTransitionGuard(wf, transition)
        guard.permissions = permissions
        workflow = self[wf]
        workflow.transitions[transition].guard = guard

    def createWorkflow( self, id ):
        """
            Creates new workflow.

            Arguments:

                'id' -- Workflow id string.

            New workflow object represents the WorkflowDefinition class instance.

        """
        ob = WorkflowDefinition(id)
        self._setObject(id, ob)

    def bindWorkflow( self, id, types=None ):
        """
            Associates the specified workflow with the particular portal types.

            Arguments:

                'id' -- Workflow id string.

                'types' -- Portal types list.

            The given workflow is added to the workflows chain corresponding to the
            specified portal type.
        """
        if types is not None:
            for typ in types:
               if self._chains_by_type is None:
                   chain=[]
               else:
                   chain = self._chains_by_type.get(typ, [])
               chain = list(chain)
               chain.append(id)
               self.setChainForPortalTypes( ( typ, ), chain )
        else:
            # Add workflow to the default chain
            chain = self._default_chain or []
            if id not in chain:
                 chain = list(chain)
                 chain.append(id)
                 self._default_chain = tuple(chain)

    def getChainFor( self, ob ):
        """
            Returns the chain that applies to the given object.

            Arguments:

                'ob' -- Either a portal object or a string representing the object's portal type.

            Result:

                List of workflow ids.
        """
        wf_id = self._getCategoryWorkflowFor( ob )
        if wf_id is not None:
            return [ wf_id ]
        return _WorkflowTool.getChainFor( self, ob )

    security.declarePublic('doActionFor')
    def doActionFor( self, ob, action, wf_id=None, wf_bycategory=1, *args, **kw ):
        """
            Allows the user to request a workflow action.

            Arguments:

                'ob' -- User context.

                'action' -- Workflow action id.

                'wf_id' -- Optional workflow specification.

                'wf_bycategory' -- Boolean. Indicates that workflow should be selected
                                   depending on the document's category.

                '*args', '**kw' -- Additional arguments to be passed to the action method.

            Result:

                Action result code.
        """
        if wf_id is None and wf_bycategory:
            wf_id = self._getCategoryWorkflowFor( ob )

        if ob.implements('isHTMLDocument'):
            ToArchive = ( action == 'ToArchive' ) and 1 or 0
            if ToArchive:
                storage_url = getRelativeURL( ob, clean=1 )
                setattr( ob, 'storage_url', storage_url )
                ob._p_changed = 1

            ToStorage = ( action == 'ToStorage' ) and 1 or 0
            if ToStorage:
                archive_url = getRelativeURL( ob, clean=1 )
                setattr( ob, 'archive_url', archive_url )
                ob._p_changed = 1

            IsBrainsReindex = ( ToArchive or ToStorage )
            state = self.getStateFor( ob, wf_id )
        else:
            IsBrainsReindex = None
            state = None

        res = self._doActionFor( ob, action, wf_id, wf_bycategory, *args, **kw )

        # get object workflow status
        workflow_history = getattr( ob, 'workflow_history', None )
        mapping = self.getCatalogVariablesFor(ob) or {}
        recursive = 0

        if res and res.has_key('should_be_moved'):
            if res.has_key('folder_to_move') and res['folder_to_move'] is not None:
                self.lock.acquire()
                try:
                    ob = res['folder_to_move'].moveObject( ob )
                finally:
                    self.lock.release()
            res = { 'ObjectMoved':1, 'ob':ob }
            recursive = 1

        if ob is None:
            raise SimpleError, 'Object was moved and not found!'

        new_state = self.getStateFor( ob, wf_id )

        if ob is not None: # and hasattr(aq_base(ob), 'reindexObject'):
            catalog = getToolByName( self, 'portal_catalog', None )
            if catalog is not None:
                mapping['allowedRolesAndUsers'] = 1
                mapping['state'] = 1
                idxs = mapping.keys()
                #ob.reindexObject(idxs=idxs)
                catalog.reindexObject( ob, idxs=idxs, recursive=recursive )

        if IsBrainsReindex:
            for task in ob.followup.objectValues():
                if not task or task.meta_type != 'Task Item':
                    continue
                task.updateIndexes( idxs=['archive'], check_path=None )
                task.reindexObject( idxs=['archive'] )

        if state is not None:
            brains_type = self.getStateDisableBrainsType( wf_id, state )
            if brains_type:
                if not self.getStateDisableBrainsType( wf_id, new_state ):
                    ob.followup.activateDisabledTasks( recursive=1, state=state, brains_type=brains_type )

        portal_log( self, 'WorkflowTool', 'doActionFor', 'new state', ( new_state, workflow_history, res ) )

        if ob.implements('isDocument'):
            ob.notifyWorkflowStateChanged()

        return res

    def _doActionFor( self, ob, action, wf_id=None, wf_bycategory=1, *args, **kw ):
        """
            Workflow action recursived method
        """
        if wf_id is None and wf_bycategory:
            wf_id = self._getCategoryWorkflowFor( ob )

        portal_log( self, 'WorkflowTool', 'doActionFor', 'action', ( ob, action, wf_id ) )

        try:
            res = _WorkflowTool.doActionFor( self, ob, action, wf_id, *args, **kw )
        except ( ConflictError, ReadConflictError ):
            raise
        except Exception, msg_error:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            message = str(msg_error)
            if message in ( 'Involved users is not defined', 
                            'Department folder is not defined', 
                            'User secretary department is not defined', ):
                #trace = ' %s' % '(WorkflowTool.doActionFor)'
                logger.info('doActionFor %s: %s, %s' % ( ob.physical_path(), exc_type, message ))
            else:
                #trace = '\n%s' % print_traceback( sys.exc_traceback )
                #portal_log( self, 'WorkflowTool', 'doActionFor', 'unexpected error', ( \
                #    ob is not None and ob.physical_path(), exc_type, msg ), \
                #    force=1 )
                portal_error('WorkflowTool.doActionFor', 'unexpected error: %s %s\n%s' % ( \
                    exc_type, exc_value, ob is not None and ob.physical_path() ), \
                    exc_info=True)
                raise
            #do not change state for document!
            raise SimpleError, msg_error

        return res or {}

    security.declarePrivate( '_invokeWithNotification' )
    def _invokeWithNotification( self, wfs, ob, action, func, args, kw ):
        """
            Private utility method:  call 'func', and deal with exceptions
            indicating that the object has been deleted or moved.
        """
        portal_log( self, 'WorkflowTool', '_invokeWithNotification', 'func', ( ob, action, func ) )
        reindex = 0
        excode = {}
        for w in wfs:
            w.notifyBefore( ob, action )
        try:
            res = apply( func, args, kw )
        except ObjectDeleted, ex:
            res = ex.getResult()
            portal_log( self, 'WorkflowTool', '_invokeWithNotification', 'ObjectDeleted', ( args, res ) )
            reindex = 0
        except ObjectMoved, ex:
            res = ex.getResult()
            portal_log( self, 'WorkflowTool', '_invokeWithNotification', 'ObjectMoved', ( args, res ) )
            ob = ex.getNewObject()
        except:
            exc_type, exc_value, exc_traceback = exc = sys.exc_info()
            #trace = print_traceback(sys.exc_traceback)
            portal_error('WorkflowTool._invokeWithNotification', 'unexpected error: %s %s\n%s' % ( \
                    exc_type, exc_value, ob is not None and ob.physical_path() ), \
                    exc_info=True)
            try:
                for w in wfs:
                    w.notifyException( ob, action, exc )
                raise exc_type, exc_value, exc_traceback
            finally:
                exc_type = exc_value = exc_traceback = exc = None
        for w in wfs:
            x = w.notifySuccess( ob, action, res )
            if x:
                excode.update( x )
        if reindex:
            self._reindexWorkflowVariables( ob )
        if excode: # and type(excode) is DictType:
            portal_log( self, 'WorkflowTool', '_invokeWithNotification', 'excode: %s' % excode )
            if excode.has_key('action'):
                next_action = excode['action']
                del excode['action']
                res = excode
                if next_action and next_action != action:
                    res.update( self._doActionFor( ob, next_action ) )
            else:
                res = excode
        return res

    security.declarePublic('getStateFor')
    def getStateFor( self, ob, wf_id=None, wf_bycategory=1, category=None ):
        """
            Returns workflow state of the object.

            Arguments:

                'ob' -- Object reference.

                'wf_id' -- Optional workflow specification.

                'wf_bycategory' -- Boolean. Indicates that workflow should be selected
                                   depending on the document's category.

                'category' -- Explicit document category specification.

            Result:

                State id.
        """
        if wf_id is None and wf_bycategory:
            wf_id = self._getCategoryWorkflowFor( ob, category=category )

        # TODO: use wf.state_var
        return _WorkflowTool.getInfoFor( self, ob, 'state', None, wf_id )

    security.declarePublic('getStateForContext')
    def getStateForContext( self, *args, **kw ):
        """
            Returns workflow state of the current context.

            Arguments:

                '*args', '**kw' -- Additional arguments to be passed to the getStateFor method.

            Result:

                State id.
        """
        return self.getStateFor( aq_parent( self ), *args, **kw )

    security.declarePublic('getInfoFor')
    def getInfoFor( self, ob, name, default=MissingValue, wf_id=None, wf_bycategory=1, *args, **kw ):
        """
            Returns information on the object provided by the workflow.

            Arguments:

                'ob' -- Object reference.

                'name' -- Workflow variable name.

                'default' -- Default variable value.

                'wf_id' -- Optional workflow specification.

                'wf_bycategory' -- Boolean. Indicates that workflow should be selected
                                   depending on the document's category.

                '*args', '**kw' -- Additional arguments to be passed to the workflow's
                                   getInforFor method.

            Result:

                Workflow variable value.
        """
        if wf_id is None and wf_bycategory:
            wf_id = self._getCategoryWorkflowFor( ob )

        if default is MissingValue:
            default = workflow_marker

        base = ob

        if name == 'review_history':
            while not (base.implements( 'isCategorial' ) or base.implements( 'isDocument' ) or base.implements( 'isContentStorage' )):
                if not base or base.implements( 'isPortalRoot' ):
                    return None
                try:
                    base = base.getBase()
                except:
                    return None

        return _WorkflowTool.getInfoFor( self, base, name, default, wf_id, *args, **kw )

    security.declarePublic('getInfoForContext')
    def getInfoForContext( self, *args, **kw ):
        """
            Returns information on the current context provided by the workflow.

            Arguments:

                '*args', '**kw' -- Additional arguments to be passed to the getInfoFor method.

            Result:

                Workflow variable value.
        """
        return self.getInfoFor( aq_parent( self ), *args, **kw )

    security.declarePrivate('getCatalogVariablesFor')
    def getCatalogVariablesFor( self, ob, wf_bycategory=1 ):
        """
            Returns a mapping containing the catalog variables that apply to the object.

            Arguments:

                'ob' -- Object reference.

                'wf_bycategory' -- Boolean. Indicates that workflow should be selected
                                   depending on the document's category.

            Result:

                Mapping containing the variables name/value pairs.
        """
        vars = _WorkflowTool.getCatalogVariablesFor( self, ob )

        if wf_bycategory:
            wf_id = self._getCategoryWorkflowFor( ob )
            if wf_id:
                wf = self.getWorkflowById( wf_id )
                if wf:
                    vars[ wf.state_var ] = wf.getInfoFor( ob, wf.state_var, None )

        return vars

    security.declarePrivate('wrapWorkflowMethod')
    def wrapWorkflowMethod( self, ob, method_id, func, args, kw ):
        """
            Allows a workflow definition to wrap a WorkflowMethod.

            Arguments:

              	'ob' -- Object reference.

                'method_id' -- Workflow method id.

                'func' -- Function reference.

                'args', 'kw' -- Additional arguments to be passed to the workflow method.

            To be invoked only by WorkflowCore.
        """
        wf = None
        wfs = self.getWorkflowsFor(ob)
        if wfs:
            for w in wfs:
                if (hasattr(w, 'isWorkflowMethodSupported')
                    and w.isWorkflowMethodSupported(ob, method_id)):
                    wf = w
                    break
        else:
            wfs = ()
        if wf is None:
            # No workflow wraps this method.
            # check permission
            if not isinstance( method_id, StringType ):
                if not _checkPermission( method_id.getPerm(), ob ):
                    raise Unauthorized
            return apply(func, args, kw)
        return self._invokeWithNotification(
            wfs, ob, method_id, wf.wrapWorkflowMethod,
            (ob, method_id, func, args, kw), {})

    def _getCategoryWorkflowFor( self, ob, category=None ):
        """
            Returns the workflow corresponding to the document's category.

            Arguments:

                'ob' -- Object reference.

                'category' -- Explicit category specification.

            Result:

                Workflow definition object.
        """
        chain = _WorkflowTool.getChainFor( self, ob )
        wf_id = None

        if chain and ob.implements( 'isCategorial' ):
            metadata = getToolByName( self, 'portal_metadata', None )
            if metadata is None:
                return None
            category = metadata.getCategoryById( category or ob.Category() )
            if category:
                wf_id = category.Workflow()
                if wf_id and wf_id not in chain:
                    wf_id = None

        return wf_id

    def onFinalize( self, task ):
        """
            Task finalization handler.

            Arguments:

              'task' -- Task item.
        """
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return
        metadata.docflowLogic.onFinalizeTask( task )
        #task.getBase().notifyWorkflowStateChanged()

InitializeClass( WorkflowTool )


class WorkflowDefinition( InstanceBase, DCWorkflowDefinition ):
    """
        ExpressSuite Workflow Definition
    """
    _class_version = 1.0

    meta_type = 'Workflow'
    title = 'ExpressSuite Workflow Definition'

    manage_options = DCWorkflowDefinition.manage_options + \
                     InstanceBase.manage_options

    security = ClassSecurityInfo()
    security.declareObjectProtected( CMFCorePermissions.ManagePortal )

    state_attr_permission_roles = None

    def __init__( self, id ):
        InstanceBase.__init__( self, id )
        self._addObject(States('states'))
        self._addObject(Transitions('transitions'))
        self._addObject(Variables('variables'))
        self._addObject(Worklists('worklists'))
        self._addObject(Scripts('scripts'))

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not InstanceBase._initstate( self, mode ):
            return 0

        self._upgrade('states', States)
        self._upgrade('scripts', Scripts)
        self._upgrade('transitions', Transitions)

        return 1
    
    def setAttributePermission( self, state_id, attr_id, permission, acquired, roles ):
        """
            Sets the permission-roles mapping for the category attribute 
            in given state.

            Arguments:
                
                'state_id' -- A state id string.
                
                'attr_id' -- An attribute id string.

                'permission' -- Name of permission to set.
                
                'acquired' -- In this context set acquired to True means 
                    "take security settings from state or superCategory`s 
                    attribute settings".
                
                'roles' -- List of roles to set.
        """
        # in this context acquired means 'take all from state or superCategory`s attribute'
        # so if acquired - drop all roles for permission
        
        sapr = self.state_attr_permission_roles
        if sapr is None:
            self.state_attr_permission_roles = sapr = PersistentMapping()
        if acquired:
            roles = [] #list(roles)
        else:
            roles = tuple(roles)
        
        pr = sapr.get( (state_id, attr_id), {})
        pr[permission] = roles
        sapr[ (state_id, attr_id) ] = pr
    
    def setAttributePermissions( self, REQUEST ):
        """
            Sets the permission-roles mapping for the category attribute in given state.
            
            Note: Only 'View' and 'Modify portal content' permissions may be changed here.

            Arguments:
                
                'REQUEST' -- specifies Zope request object.
        """
        # in this context acquired means 'take all from state or superCategory`s attribute'
        # so if acquired - drop all roles for permission
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return
        available_roles = metadata.getManagedRoles_()

        state = REQUEST.get('state')
        attr_id = REQUEST.get('attribute_id')

        sapr = self.state_attr_permission_roles
        if sapr is None:
            self.state_attr_permission_roles = sapr = PersistentMapping()

        for p in ( CMFCorePermissions.View, CMFCorePermissions.ModifyPortalContent, CMFCorePermissions.ManageProperties, ):
            roles = []
            acquired = REQUEST.get('acquire_' + p, 0)
            for r in available_roles:
                if REQUEST.get('%s|%s' % (p, r), 0):
                    roles.append(r)
            roles.sort()
            if not acquired:
                roles = tuple(roles)
            else:
                roles = []

            pr = sapr.get( (state, attr_id), {})
            pr[p] = roles
            sapr[ ( state, attr_id ) ] = pr

    def getAttributePermissionInfo( self, state_id, attr_id, p ):
        """
            Returns information about permission settings for 
            category attribute in given state.

            Arguments:

                'state_id' -- A state id string.
                
                'attr_id' -- An attribute id string.
                
                'p' -- Permission name.

            Result:

                Dictionary with two keys: 'acquired' and 'roles'. 'acquired' 
                is true if no permission-roles mapping for category attribue
                specified. Roles are list of roles managed by permission.
        """
        roles = None
        perm = None
        if self.state_attr_permission_roles:
            perm_def = self.state_attr_permission_roles.get( (state_id, attr_id), {} )
            roles = perm_def.get(p, None)
        if roles is None:
            return {'acquired':1, 'roles':[]}
        else:
            if type(roles) is TupleType:
                acq = 0
            else:
                acq = 1
            return {'acquired':acq, 'roles':list(roles)}

    def listObjectActions( self, info ):
        """
            Lists object actions provided by the workflow.

            Arguments:

                'info' -- Object action information. See CMFCore.ActionsTool for details.

            Allows this workflow to include actions to be displayed in the actions box.
            Called only when this workflow is applicable to info.content.

            Result:

                List of actions represented by mappings with the following keys: 'name',
                'url', 'permissions', 'category'.
        """
        try:
            ob = info.content
            if ob.implements('isLockable'):
                ob.failIfLocked()
        except ResourceLockedError:
            return []
        return DCWorkflowDefinition.listObjectActions( self, info )

    def notifyBefore( self, ob, action ):
        """
            Before transition handler.

            Arguments:

                'ob' -- Object reference.

                'action' -- Workflow action id.
        """
        portal_log( self, 'WorkflowDefinition', 'notifyBefore', 'action', ( ob, action ) )
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return
        metadata.versionWorkflowLogic.onBeforeTransition( ob, action )
        metadata.docflowLogic.onBeforeTransition( ob, action )

    def notifySuccess( self, ob, action, result ):
        """
            After transition handler.

            Arguments:

                'ob' -- Object reference.

                'action' -- Workflow action id.
        """
        portal_log( self, 'WorkflowDefinition', 'notifySuccess', 'action', ( ob, action, result ) )
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return None
        return metadata.docflowLogic.onAfterTransition( ob, action )

    security.declarePrivate('isWorkflowMethodSupported')
    def isWorkflowMethodSupported( self, ob, method ):
        """
            Checks whether the given workflow method is supported in the current state.

            Arguments:

                'ob' -- Object reference.

                'method' -- Either a workflow method reference or method id string.
        """
        if not isinstance( method, StringType ):
            method_id = method.getAction()
        else:
            method_id = method

        sdef = self._getWorkflowStateOf(ob)

        if sdef is None:
            return 0
        if method_id in sdef.transitions:
            tdef = self.transitions.get(method_id, None)
            if (tdef is not None and tdef.trigger_type == 2 and # 2:=TRIGGER_WORKFLOW_METHOD
                self._checkTransitionGuard(tdef, ob)):
                return 1
        return 0

    security.declarePrivate('wrapWorkflowMethod')
    def wrapWorkflowMethod( self, ob, method, func, args, kw ):
        """
            Allows the user to request a workflow action.

            Arguments:

                'ob' -- Object reference.

                'method_id' -- Workflow method id.

                'func' -- Function reference.

                'args', 'kw' -- Additional arguments to be passed to the workflow method.

            Note:

                Workflow method must perform its own security checks.
        """
        if not isinstance( method, StringType ):
            method_id = method.getAction()
            invoke_after = method.getInvokeAfter()
        else:
            method_id = method
            invoke_after = None

        sdef = self._getWorkflowStateOf(ob)
        if sdef is None:
            raise WorkflowException, 'Object is in an undefined state'
        if method_id not in sdef.transitions:
            raise Unauthorized
        tdef = self.transitions.get(method_id, None)
        if tdef is None or tdef.trigger_type != 2: # 2:=TRIGGER_WORKFLOW_METHOD
            raise WorkflowException, (
                'Transition %s is not triggered by a workflow method'
                % method_id)
        if not self._checkTransitionGuard(tdef, ob):
            raise Unauthorized
        if not invoke_after:
            res = apply(func, args, kw)
        try:
            self._changeStateOf(ob, tdef)
        except ObjectDeleted:
            # Re-raise with a different result.
            raise ObjectDeleted(res)
        except ObjectMoved, ex:
            # Re-raise with a different result.
            raise ObjectMoved(ex.getNewObject(), res)
        if invoke_after:
            res = apply(func, args, kw)
        return res

    security.declarePrivate('getCategoryDefinition')
    def getCategoryDefinition( self ):
        """
            Returns the document category definition object applied to this workflow.

            Result:

                Category definition object.
        """
        # XXX Too slow
        metadata = getToolByName( self, 'portal_metadata', None )
        if metadata is None:
            return None
        categories = metadata.listCategories()
        for category in categories:
             workflow = category.getWorkflow()
             if workflow and aq_base(workflow) is aq_base(self):
                 return category
        return None

InitializeClass( WorkflowDefinition )

addWorkflowFactory(WorkflowDefinition, id='app_workflow', title='ExpressSuite workflow')


class WorkflowMethod( Method ):
    """ 
        Wrap a method to workflow-enable it
    """
    _need__name__ = 1

    def __init__( self, method, id=None, reindex=1, security=None, invoke_after=None, method_permission=None ):
        self._m = method
        if id is None:
            id = method.__name__
        self._id = id
        self._invoke_after = invoke_after
        self._method_permission = method_permission
        security.declarePublic( 'edit' )
        # reindex ignored since workflows now perform the reindexing.

    def __call__( self, instance, *args, **kw ):
        """
            Invoke the wrapped method, and deal with the results.
        """
        wf = getToolByName(instance, 'portal_workflow', None)
        res = wf.wrapWorkflowMethod(instance, self, self._m, #._id
                                   (instance,) + args, kw)
        return res

    def getAction( self ):
        return self._id

    def getInvokeAfter( self ):
        return self._invoke_after

    def getPerm( self ):
        return self._method_permission


class ContainerMapping( PersistentMapping, Implicit ):
    """
        Dictionary-like class that allows attributes to be dynamically inherited
        from base categories
    """
    def isPrivateKey( self, key ):
        """
            Checks whether the attribute with the given key is private.

            Arguments:

                'key' -- Attribute name.

            Result:

                Boolean. Returns True value for private attribute and False
                value for attribute inherited from another category.
        """
        return self.data.has_key(key)

    def has_key( self, key ):
        return key in self.keys()

    def keys( self ):
        data = self._getData()
        return data and data.keys() or []

    def get( self, name, default=None ):
        data = self._getData()
        return data.get(name, default)

    def __getitem__( self, name ):
        return self.get(name)

    def __setitem__( self, name, value ):
        self.data[name] = value
        self._p_changed = 1

    def __delitem__( self, name ):
        del self.data[name]
        self._p_changed = 1

    def _getData( self ):
        """
            Returns the mapping representing dictionary data.

            Dynamically inherited attributes are included into mapping as well
            as private attributes.

            Dictionary data are being automatically cached; cache is updated
            every time the '__setattr__' method is called on the ContainerMapping
            class instance.
        """
        if hasattr(self, 'data_cache'):
            data_cache = getattr( self, 'data_cache', None )
            if data_cache is not None:
               return data_cache

        parent = aq_parent(aq_inner( self ))
        workflow = aq_parent(aq_inner( parent ))
        if workflow is None:
            # happens in process of lifting the parent from DB
            return self.data

        category = workflow.getCategoryDefinition()
        if category is None:
            # workflow is not bound to any category
            return self.data
        else:
            mapping = {}
            id = parent.getId()
            bases = list(category.listBases())
            bases.reverse()
            for base in bases:
                wf = base.__of__(self).getWorkflow()
                container = getattr(wf, id, None)
                if container:
                    mapping.update(container._mapping._getData())

            mapping.update( self.data )
            setattr( self, 'data_cache', mapping )
            return mapping

        return self.data

    def invalidateDataCache( self ):
        """
            Forces data cache to be updated
        """
        try:
            del self.data_cache
        except AttributeError:
            return
        except KeyError:
            pass

        category = self.getCategoryDefinition()
        if category is not None:
            id = aq_parent(self).getId()
            for cdef in category.listDependentCategories():
                wf = cdef.__of__(self).getWorkflow()
                container = getattr(wf, id, None)
                if container:
                   try:
                       del container._mapping.data_cache
                   except KeyError:
                       pass

InitializeClass( ContainerMapping )

class ContainerTab( Persistent, _ContainerTab ):
    _class_version = 1.0

    def __init__( self, id ):
        self._mapping = ContainerMapping()
        Persistent.__init__(self)
        self.id = id

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        # initialize attributes
        if not Persistent._initstate( self, mode ):
            return 0

        mapping = self._mapping
        if type(mapping) is DictType:
            self._mapping = ContainerMapping( mapping )
        elif mode and mapping._p_oid is None: # < 1.3
            if hasattr( mapping, '_v_data_cache' ):
                del mapping._v_data_cache
            self._p_changed = mapping._p_changed = 1

        return 1

    def __getattr__( self, name ):
        if hasattr(self, '_mapping'):
            ob = self._mapping.get(name, None)
            if ob is not None:
                return ob
        raise AttributeError, name

    def _setOb( self, name, value ):
        _ContainerTab._setOb(self, name, value)
        self.notifyChanged()

    def _delOb( self, name ):
        _ContainerTab._delOb(self, name)
        self.notifyChanged()

    def isPrivateItem( self, item ):
        """
            Checks whether the container's item is private.

            Arguments:

                'item' -- Either a container's object reference or an attribute
                          id string.

            Result:

                Boolean. Returns True value for private attribute and False
                value for attribute inherited from another category.
        """
        if item is StringType:
            item = self[item]

        return self._mapping.isPrivateKey(item.getId())

    def makePrivateItem( self, item ):
        """
            Makes the container's item private.

            Arguments:

                'item' -- Either a container's object reference or an attribute
                          id string.

            Result:

                Item instance.

            Ensures that the given item is private or copies it to the current
            object in case it is inherited from another category.
        """
        if item is StringType:
            item = self[item]

        id = item.getId()
        if not self.isPrivateItem(item):
            self._setObject(id, item._getCopy(self))

        return self[id]

    def _checkId( self, id, allow_dup=0 ):
        if not allow_dup:
            if self._mapping.isPrivateKey(id):
                raise 'Bad Request', 'The id "%s" is already in use.' % id
        return

    def notifyChanged( self ):
        """
            Handler for the container contents changes.

            Note:

                Handler is _not_ invoked on changing the contained
                itemsm properies; it's only purpose is to track the items
                creation and deletion operations in order to update the data
                cache.
        """
        self._mapping.invalidateDataCache()

InitializeClass( ContainerTab )

class Scripts( ContainerTab, _Scripts ):
    """
        Workflow scripts container
    """
    manage_main = _Scripts.manage_main

InitializeClass( Scripts )

class States( ContainerTab, _States ):
    """
        Workflow states container
    """
    all_meta_types = ( { 'name' : StateDefinition.meta_type, 'action' : 'addState', }, )
    manage_main = _States.manage_main

InitializeClass( States )

class Transitions( ContainerTab, _Transitions ):
    """
        Workflow transitions container
    """
    all_meta_types = ( { 'name' : TransitionDefinition.meta_type, 'action' : 'addTransition', }, )
    manage_main = _Transitions.manage_main

InitializeClass(Transitions)
