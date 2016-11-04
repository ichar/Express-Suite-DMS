## Script (Python) "workflows"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=allowed_users=[]
##title=
##
from Products.ExpressSuiteTools.SecureImports import portal_log

REQUEST = context.REQUEST

member = context.portal_membership.getAuthenticatedMember()
username = member.getUserName()

wf = context.getWorkflow()
wf_id = wf.getId()
params = None
info = {}

portal_workflow = context.portal_workflow

if REQUEST.has_key('save_properties'):
    #Saving workflow properties
    portal_workflow.setProperties(wf_id, REQUEST['title'])
    action = 'workflow_properties'
    message = 'Properties changed'

elif REQUEST.has_key('addState'):
    #Adding new state
    state_id = REQUEST.get('state_id')
    if state_id:
        portal_workflow.addState(wf_id, state_id)
    action = 'workflow_states'
    message = 'State added'

elif REQUEST.has_key('deleteStates'):
    #Deleting state(s)
    ids = REQUEST.get('ids') or []
    if ids:
        portal_workflow.deleteStates(wf_id, ids)
    action = 'workflow_states'
    message = 'State(s) removed'

elif REQUEST.has_key('save_state'):
    #Saving state properties
    transitions = REQUEST.get('transitions', [])
    state = REQUEST.get('state')
    title = REQUEST.get('title')
    
    # only one version can exist in state
    only_one_version_can_exists = REQUEST.get('only_one_version_can_exists', None)
    if only_one_version_can_exists:
        action = 'add'
        transition_for_exclude = REQUEST.get('transition_for_exclude')
    else:
        action = 'remove'
        transition_for_exclude = None

    disable_brains_type = REQUEST.get('disable_brains_type')
    context.manageAllowSingleStateForVersionArray( action, state, transition_for_exclude )
    portal_workflow.setStateProperties( wf_id, state, title, transitions, disable_brains_type )
    action = 'state_properties'
    message = 'State properties changed'
    params = { 'state': state }

elif REQUEST.has_key('set_permissions'):
    state = REQUEST.get('state')
    force_update_roles = REQUEST.get('force_update_roles')
    portal_workflow.setStatePermissions(wf_id, state, REQUEST, None, force_update_roles)
    action = 'state_properties'
    message = 'State permissions changed'
    params = { 'state': state }

elif REQUEST.has_key('set_attr_permissions'):
    state = REQUEST.get('state')
    attribute_id = REQUEST.get('attribute_id')
    wf.setAttributePermissions(REQUEST)
    action = 'workflow_attributes_permissions'
    message = 'State permissions changed'
    params = { 'state': state, 'attr': attribute_id }

elif REQUEST.has_key('setInitialState'):
    ids = REQUEST.get('ids')
    if ids:
        wf.states.setInitialState(ids and ids[0])
    action = 'workflow_states'
    message = 'Initial state selected'

elif REQUEST.has_key('addTransition'):
    trans_id = REQUEST.get('trans_id')
    if trans_id:
        portal_workflow.addTransition(wf_id, trans_id)
    action = 'workflow_transitions'
    message = 'Transition added'

elif REQUEST.has_key('deleteTransitions'):
    ids = REQUEST.get('ids') or []
    if ids:
        portal_workflow.deleteTransitions(wf_id, ids)
    action = 'workflow_transitions'
    message = 'Transition(s) removed'

elif REQUEST.has_key('addManagedPermission'):
    p = REQUEST.get('p')
    wf.addManagedPermission(p)
    action = 'workflow_permissions'
    message = 'Permission added'

elif REQUEST.has_key('delManagedPermissions'):
    ids = REQUEST.get('ids')
    wf.delManagedPermissions(ids)
    action = 'workflow_permissions'
    message = 'Permission(s) removed'

elif REQUEST.has_key('save_transition'):
    transition = REQUEST['transition']
    info['transition'] = transition
    title = REQUEST['title']
    info['title'] = title
    guard_roles = REQUEST.get('guard_roles', [])
    info['guard_roles'] = guard_roles
    new_state_id = REQUEST['new_state_id']
    info['new_state_id'] = new_state_id
    actbox_name = REQUEST['actbox_name']
    info['actbox_name'] = actbox_name
    guard_permissions = REQUEST.get('guard_permissions', [])
    info['guard_permissions'] = guard_permissions
    allowed_users = REQUEST.get('allowed_users', [])
    info['allowed_users'] = allowed_users

    IsEverybody = not allowed_users and 1 or 0

    if IsEverybody:
        expression = "python: here.Category() == '%s'" % context.getId()
    else:
        expression = "python: here.Category() == '%s' and here.AuthenticatedUser() in %s" % ( context.getId(), allowed_users )

    trigger_type = REQUEST.get('trigger_type', '1' )
    info['trigger_type'] = trigger_type

    portal_workflow.setTransitionProperties( wf_id, transition, title, actbox_name, new_state_id, trigger_type )
    portal_workflow.setTransitionGuardRoles( wf_id, transition, guard_roles )
    portal_workflow.setTransitionGuardRules( wf_id, transition, expression )
    portal_workflow.setTransitionGuardPermissions( wf_id, transition, guard_permissions )

    action = 'transition_properties'
    message = 'Transition properties changed'
    params = {'transition': transition}

else:
    action = None
    message = 'Nothing to changed'

portal_log( context, 'workflows', 'action', 'changed by %s' % username, ( action, message, params, info ), force=1 )
REQUEST['RESPONSE'].redirect( context.absolute_url( action=action, message=message, params=params ) )
