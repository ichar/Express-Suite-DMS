## Script (Python) "manage_workflows"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##title=
##

REQUEST = context.REQUEST
c_id = context.getId()
wf = context.Workflow()

if REQUEST.has_key('save_transition2tasktemplate'):
    for transition_id in context.portal_workflow[wf].transitions.objectIds():
        task_templates = REQUEST.get( transition_id+'_task_templates', [])
        context.portal_metadata.setTransitionTaskTemplate( c_id, transition_id, task_templates )
    context.redirect( action='task_template_summary', fragment='transition2tasktemplate' )

if REQUEST.has_key('save_state2tasktemplatedie'):
    for state_id in context.portal_workflow[wf].states.objectIds():
        task_templates_array = {}  # { 'task_template_id1': 'result_code1', ... }
        task_templates = REQUEST.get( state_id+'_task_templates', [])
        if task_templates != []:
            for template_id in task_templates:
                select_name = '%s_result_code_%s' % ( state_id, template_id )
                result_code = REQUEST.get(select_name)
                if result_code == '':
                     result_code=None
                task_templates_array[template_id] = result_code
        context.portal_metadata.setState2TaskTemplateToDie( c_id, state_id, task_templates_array )
    context.redirect( action='task_template_summary', fragment='state2tasktemplatedie' )

if REQUEST.has_key('save_state2transition'):
    for state_id in context.portal_workflow[wf].states.objectIds():
        title = context.portal_workflow[wf].states[state_id].title
        transitions = REQUEST.get( state_id+'_transitions', [])
        context.portal_workflow[wf].states[state_id].setProperties(
          title=title,
          transitions=transitions
        )
    context.redirect( action='task_template_summary', fragment='state2transition' )
