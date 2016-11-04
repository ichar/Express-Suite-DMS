"""
Docflowlogic class
$Id: DocflowLogic.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, ERROR, TRACE
from types import StringType

from Products.CMFCore.utils import getToolByName

from Acquisition import Implicit, aq_base, aq_get

from Config import TaskResultCodes
from SimpleObjects import Persistent
from PortalLogger import portal_log

from Utils import InitializeClass, UnrestrictedCheckObject

APPLY_AUTOMATED = None


class DocflowLogic( Persistent, Implicit ):
    """
        DocflowLogic class.

        Handled events:

            - onBeforeTransition
            - onAfterTransition
            - onFinalizeTask

        Logic:

           - onBeforeTransition:
               1. take listTaskTemplateForDie for new state
               2. if doc have task from that list, off flag 'automated_task' (i.e. task_template_id),
                  finalize that task, and set result code (if not finalized)

           - onAfterTransition:
               1. take task templates needed for activate for transition,
               2. activate all them

           - onFinalizeTask:
               1. are finalized task automated? if no - exit
               2. take list of result codes of finalized automated-task of document
               3. take transition from matrix "result-codes -> transition"
                  if exists - make this transition

         Diagrams:

             'docflow-class_diagram.png' -- UML diagram of docflow classes
    """
    def __init__( self ):
        Persistent.__init__( self )

    def _initstate( self, mode ):
        """ 
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        return 1

    def onBeforeTransition( self, ob, action ):
        """
            Handler-function are called before transition.

            Arguments:

                'ob' -- object in context of which happened transition (generally HTMLDocument)

                'action' -- transition id.

            Performs DocFlow action for transition.

                0. check object (_isObjectValid)
                1. take list of task for finalize in new state
                2. for each automated task of document,
                   2.1  if task are included in list:
                     - make flag 'not automated'
                     - finalize task (if not)
        """
        if not self._isObjectValid( ob ):
            return
        if not isinstance( action, StringType ):
            action = action.getAction()

        # 1. take listTaskTemplateForDie for new state
        category_id = self._getCategoryOfObject( ob )
        current_state = self._getStateOfObject( ob )
        state = self._stateWhereDocumentGo( ob, action )

        # list of template's id, with result code (look task_template_summary.dtml, action_task_template_summary codes!)
        listTaskForDie = self._getListTaskForDieForState( category_id, state )

        portal_log( self, 'DocflowLogic', 'onBeforeTransition', 'action, state (current, new), tasks', ( \
            action, current_state, state, listTaskForDie ) )

        # 2. if doc have task from that list, off flag 'automated_task' (i.e. task_template_id)
        #    finalize that task, and set result code,
        #    also check signature requests result
        for task in self._getTaskAutomatedOfDocument( ob ):
            template_id = self._getTaskTemplateId( task )
            IsSignature = template_id in ( 'SelfSignature', 'makeTaskToSign', ) and \
                state in ( 'evolutive', 'OnWork', 'private', ) and 1 or 0
            if template_id in listTaskForDie.keys():
                self._makeTaskNotAutomated( task )
                if not task.isFinalized():
                    #portal_log( self, 'DocflowLogic', 'onBeforeTransition', 'finalize this task', task.id )
                    self._finalizeTask( task, listTaskForDie[template_id] ) # result_code
            elif IsSignature:
                self._makeTaskNotAutomated( task )
                self._finalizeTask( task, TaskResultCodes.TASK_RESULT_CANCELLED )

    def onAfterTransition( self, ob, action ):
        """
            Handler-function are called after transition.

            Arguments:

                'ob' -- object in context of which transition happened (generally HTMLDocument)

                'action' -- transition id

            Performs:

                1. get action templates for activating in new state
                2. for each action template - activate it
        """
        uid = ob.getUid()
        portal_log( self, 'DocflowLogic', 'onAfterTransition', 'action', ( ob, action, uid ) )

        if not self._isObjectValid( ob ):
            return
        if not isinstance( action, StringType ):
            action = action.getAction()

        # 1. take task templates needed for activations for transition
        #    activate all them
        transition = action
        category_id = self._getCategoryOfObject( ob )
        excode = {}

        for template_id in self._getTemplatesForTransition( category_id, transition ):
            #ob = UnrestrictedCheckObject( self, ob )
            portal_log( self, 'DocflowLogic', 'onAfterTransition', 'activate template', template_id )
            x = self._activateTemplate( category_id, template_id, ob, transition )
            if x: excode.update( x )

        portal_log( self, 'DocflowLogic', 'onAfterTransition', 'state changed', ( \
                    self._getStateOfObject( ob ), excode ) )
        return excode

    def onFinalizeTask( self, task ):
        """
            Event-handler function on any finalize of task.

            Arguments:

                'task' -- finalized task (TaskItem)

            When task are finalized, we must to check, is task automated,
            if yes, take list of result codes all 'automated' tasks of this document,
            then based on this list ask about transition, if transition exists - perform transition
        """
        task_id = task.getId()
        task_template_id = task.TaskTemplateId()
        IsAutomated = self._isTaskAutomated( task )
        #portal_log( self, 'DocflowLogic', 'onFinalizeTask', 'isFinalized, IsAutomated', ( task, task.isFinalized(), task_id, IsAutomated ) )

        # 1. are finalized task automated, if no - exit
        if not IsAutomated:
            return

        # 2. check if base is portal root, return
        ob = task.getBase()
        if ob is None or ob.implements('isPortalRoot'):
            return

        # 3. check nested items with given template id
        #    if not finalized, return
        if not task.isFollowupFinalized( task_template_id, ob ):
            return

        # 4. take list of result codes of finalized automated-task of document
        resultCodes = self._getResultCodesForTaskOfDocument( ob, self._getVersionFromTask( task ), task_id=task_id )
        #portal_log( self, 'DocflowLogic', 'onFinalizeTask', 'resultCodes', ( resultCodes, task_id ) )

        # 5. take transition for list of result-codes
        #    if exists - make it transition
        state = self._getStateOfObject( ob )
        transition = self._getTransitionByResultCodes( self._getCategoryOfObject(ob), resultCodes, state )
        portal_log( self, 'DocflowLogic', 'onFinalizeTask', 'transition for result codes %s' % resultCodes, \
                    transition )

        if transition == '':
            return

        # 6. perform transition
        self._makeTransitionForVersion( ob, transition, self._getVersionFromTask( task ) )

    def _isObjectValid( self, object ):
        """
            Check is object valid for performs docflow logic.

            Arguments:

                'object' -- object in context of which events happened (generally  HTMLDocument)

            Result:

                Boolean
        """
        return hasattr(aq_base(object), 'followup')

    def _isTaskAutomated( self, task ):
        """
            Check is task automated

            Arguments:

                'task' -- object task (TaskItem)

            Result:

                Boolean

            Task on document may be 'automated' if they was maded automated,
            or 'not automated'
        """
        if APPLY_AUTOMATED:
            if hasattr(task, '_automated'):
                return getattr(task, '_automated', None)
            elif self._getTaskTemplateId( task ) is not None:
                setattr(task, '_automated', 1)
            else:
                setattr(task, '_automated', 0)
            return getattr(task, '_automated', None)
        else:
            return self._getTaskTemplateId( task ) is not None

    def _makeTaskNotAutomated( self, task ):
        """
            Make task not automated

            Arguments:

                'task' -- task object (TaskItem)

            TaskItem have attribute 'task_template_id', which are not None, if task
            are automated (i.e. was maden automated based on task template with id
            'task_template_id')
        """
        if APPLY_AUTOMATED:
            IsAutomated = getattr(task, '_automated', None)
            #portal_log( self, 'DocflowLogic', '_makeTaskNotAutomated', 'task', ( task, IsAutomated ) )
            setattr(task, '_automated', None)
        else:
            #portal_log( self, 'DocflowLogic', '_makeTaskNotAutomated', 'task', task )
            task.task_template_id = None

    def _getTaskTemplateId( self, task ):
        """
            Get id of template, based on which task was maden.

            Arguments:

                'task' -- object task (TaskItem)

            Result:

                return template id, based on which task was created (None if not)

            TaskItem have attribute 'task_template_id' which are 'None',
            if task are not automated.
        """
        task_template_id = getattr(task, 'task_template_id', None)
        return task_template_id

    def _getResultCodesForTaskOfDocument( self, ob, version_id, task_id=None ):
        """
            Takes result codes of finalized and automated tasks of document.

            Arguments:

                'ob' -- object for which we want to take results

                'version_id' -- version on object, for which we takes tasks (result codes)

            Result:

                dictionary, with keys 'template_id', and values 'result_code',
                also there is 'special' reault_codes which mean: running task
                '__running__', and not existing in list of document's tasks:
                '__notexists__'
        """
        resultCodes = {}

        for task in ob.followup.getBoundTasks( version_id ):
            if task_id and task_id != task.getId():
                continue
            
            TID = self._getTaskTemplateId(task)
            result_code = task.ResultCode()
            
            if task.isFinalized() and self._isTaskAutomated( task ):
                resultCodes[TID] = result_code
            
            # mark running action templates
            if not task.isFinalized() and self._isTaskAutomated( task ):
                resultCodes[TID] = '__running__'
            
            # mark not existing action templates
            for action_template_id in ob.getCategory().taskTemplateContainer.getTaskTemplateIds( filter = 'have_result_codes' ):
                if not resultCodes.has_key( action_template_id ):
                    resultCodes[action_template_id ] = '__notexists__'

        return resultCodes

    def _getTransitionByResultCodes( self, category_id, result_codes, state ):
        """
            Takes transition by result codes, if is.

            Arguments:

                'category_id' -- category id

                'result_codes' -- array of result codes

                'state' -- state id for additions conditions

            Result:

                transition id or None
        """
        return self._portal_metadata().getCategoryById( category_id ).resultcodes2TransitionModel.getTransitionByResultCodes( result_codes, state )

    def _makeTransitionForVersion( self, ob, transition, version ):
        """
            Perform transition for version of object.

            Arguments:

                'ob' -- object for which performs transition

                'transition' -- transition id to perform

                'version' -- version of object
        """
        portal_log( self, 'DocflowLogic', '_makeTransitionForVersion', 'transition', transition )
        self._secureBeforeTransition( self._getTransitionObject( ob, transition ) )
        
        # enter to version
        if version:
            back_version_id = ob.version[version].makeCurrent()

        self._portal_workflow().doActionFor( ob, transition )

        self._secureAfterTransition( self._getTransitionObject( ob, transition ))
        # leave version
        if version:
            ob.version[back_version_id].makeCurrent()

    def _secureBeforeTransition( self, transition_object ):
        #portal_log( self, 'DocflowLogic', '_secureBeforeTransition', 'transition_object', transition_object )
        guard_object = transition_object.guard
        guard_object.__class__._check = secure_check
        guard_object.__dict__['check'] = guard_object._check

    def _secureAfterTransition( self, transition_object ):
        #portal_log( self, 'DocflowLogic', '_secureAfterTransition', 'transition_object', transition_object )
        guard_object = transition_object.guard
        try:
            del guard_object.__dict__['check']
        except:
            pass
        try:
            del guard_object.__class__._check
        except:
            pass

    def _getTransitionObject( self, ob, transition_id ):
        """
            Returns transiton object by id.

            Arguments:

                'ob' -- object

                'transition_id' -- transition id

            Result:

                return transition object
        """
        #portal_log( self, 'DocflowLogic', '_getTransitionObject', 'ob, transition', ( ob, transition_id ) )
        return self._portal_workflow()[self._getWorkflowId(ob)].transitions[transition_id]

    def _getVersionFromTask( self, task ):
        """
            Takes version for which task was created.

            Arguments:

                'task' -- task object (TaskItem)

            Result:

                version id of document, for which task was created
        """
        return getattr( task, 'version_id', None )

    def _stateWhereDocumentGo( self, ob, transition_id ):
        """
            Return state where document will go by transition.

            Arguments:

                'ob' -- object

                'transition_id' -- transition which will be perform

            Result:

                return state id where transition id lead
        """
        transitionInfo = self._portal_workflow().getTransitionInfo( self._getWorkflowId( ob ), transition_id )
        return transitionInfo["new_state_id"]

    def _getWorkflowId( self, ob ):
        """
            Return workflow id of object.

            Arguments:

                'ob' -- object

            Result:

                return workflow id
        """
        return self._portal_metadata().getCategoryById( ob.Category() ).Workflow()

    def _getListTaskForDieForState( self, category_id, state_id ):
        """
            Gets templates id which needed to finalize.

            Arguments:

                'category_id' -- category id

                'state_id' -- state id

            Result:

                Returns array:
                >>  taskTemplateToDie = {
                >>     'task_template_id1': 'result_code1',
                >>     ...,
                >>  }
        """
        try:
            taskTemplateToDie = self._portal_metadata().getCategoryById(category_id).state2TaskTemplateToDie[state_id]
        except:
            taskTemplateToDie = {}
        return taskTemplateToDie

    def _getTaskAutomatedOfDocument( self, ob ):
        """
            Return automated task of document.

            Arguments:

                'ob' -- object

            Result:

                Returns array of task objects (TaskItem) which was automated maden
        """
        if getattr(ob, 'followup', None) is None:
            return []
        automatedTasks = []
        # we take tasks only object's version
        for task in ob.followup.getBoundTasks( version_id=self._getObjectVersion( ob ) ):
            if self._isTaskAutomated( task ):
                automatedTasks.append( task )
        #portal_log( self, 'DocflowLogic', '_getTaskAutomatedOfDocument', 'automatedTasks', automatedTasks )
        return automatedTasks

    def _getObjectVersion( self, object ):
        """
            Returns object's version.

            Arguments:

                'object' -- object version of which we want to know

            Result:

                current version id of document
        """
        return object.getVersion().id

    def _finalizeTask( self, task, result_code ):
        """
            Finalize task with result code.

            Arguments:

                'task' -- task which neede to finalize (TaskItem)

                'result_code' -- result code by which needed to finalize task
        """
        portal_log( self, 'DocflowLogic', '_finalizeTask', 'task, result_code', ( task, result_code ) )
        task.get_brains().onFinalize( result_code=result_code )

    def _getTemplatesForTransition( self, category_id, transition_id ):
        """
            Resturn action templates which are associated with specific transition.

            Arguments:

                'category_id' -- category id

                'transition_id' -- transition id

            Result:

                array of ids of task templates (action templates) which was associated
                with specific transition of category.
        """
        res = []

        try: 
            templateIds = self._portal_metadata().getCategoryById(category_id).transition2TaskTemplate[transition_id]
        except: 
            templateIds = []

        if not templateIds:
            return res

        sorted_templates = []

        for id in templateIds:
            if id.startswith( 'before_' ):
                x = ( 0, id )
            elif id.startswith( 'after_' ):
                x = ( 8, id )
            elif id.startswith( 'move_' ):
                x = ( 9, id )
            else:
                x = ( 1, id )
            sorted_templates.append( x )

        sorted_templates.sort()
        res = [ x[1] for x in sorted_templates ]

        portal_log( self, 'DocflowLogic', '_getTemplatesForTransition', 'sorted_templates', res )
        return res

    def _getCategoryOfObject( self, ob ):
        """
            Returns category of object.

            Arguments:

                'ob' -- object

            Result:

                category id of object
        """
        return ob.Category()

    def _getStateOfObject( self, ob ):
        """
             Returns state of object.

             Arguments:

                 'ob' -- object to get state

            Result:

                State id of the object
        """
        state = self._portal_workflow().getStateFor( ob, self._getWorkflowId( ob ) )
        return state

    def _activateTemplate( self, category_id, template_id, ob, transition ):
        """
            Activate task template (action template).

            Arguments:

                'category_id' -- category id

                'template_id' -- task template (action template) to activate

                'ob' -- object in context of which activate will be performed
        """
        portal_log( self, 'DocflowLogic', '_activateTemplate', 'category_id, template_id, transition, ob', ( \
            category_id, template_id, transition, ob ) )
        return self._portal_metadata().getCategoryById( category_id ).taskTemplateContainer.activateTaskTemplate( template_id, ob, transition )

    def _portal_metadata( self ):
        return getToolByName( self, 'portal_metadata', None )

    def _portal_workflow( self ):
        return getToolByName( self, 'portal_workflow', None )


from Products.DCWorkflow.Expression import StateChangeInfo, createExprContext

def secure_check( self, sm, wf_def, ob, comment=None ):
    expr = self.expr
    if expr is not None:
        econtext = createExprContext(StateChangeInfo(ob, wf_def))
        res = expr(econtext)
        if not res:
            return 0
    return 1

InitializeClass( DocflowLogic, __version__ )
