## Script (Python) "registry_options"
##parameters=
##title=Add a report item
from Products.ExpressSuiteTools.SecureImports import portal_log

REQUEST = context.REQUEST
r = REQUEST.get

member = context.portal_membership.getAuthenticatedMember()
changed = r('changed').split(':')
last_id = REQUEST.has_key('last_id') and r('last_id') or None

if 'last_id' in changed and context.registry_id_exists( rnum=last_id ):
    message = "Registry Id exists! Duplicated entries is not allowed $ : %s $ error" % last_id
    if REQUEST is not None:
        REQUEST['RESPONSE'].redirect(context.absolute_url(action='registry_options_form', message=message))
elif member is not None:
    portal_log( context, 'registry_options', 'registry', 'object', context.physical_path(), force=1 )
    username = member.getUserName()
    if 'title' in changed or 'description' in changed:
        title = r('title')
        description = r('description')
        context.editMetadata( title=title, description=description )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'title or description', ( title, description ), force=1 )
    if 'department' in changed:
        department = r('department')
        context.setDepartment( department )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'department', department, force=1 )
    if 'tasks_max' in changed:
        tasks_max = r('tasks_max')
        context.setViewTaskCount( tasks_max )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'tasks_max', tasks_max, force=1 )
    if 'reg_num_forming_rule' in changed:
        reg_num_forming_rule = r('reg_num_forming_rule')
        context.setRegNumFormingRule( reg_num_forming_rule )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'reg_num_forming_rule', reg_num_forming_rule, force=1 )
    #if 'parent_registry' in changed:
    #    parent_registry = r('parent_registry')
    #    context.setParentRegistry( parent_registry )
    if 'default_category' in changed:
        default_category = r('default_category')
        context.setDefaultCategory( default_category )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'default_category', default_category, force=1 )
    if 'default_states' in changed:
        context.setDefaultStates( REQUEST=REQUEST )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'default_states', force=1 )
    if 'current_registry' in changed:
        current_registry = r('current_registry')
        context.setCurrentRegistry( current_registry )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'current_registry', current_registry, force=1 )
    if 'author_can_delete_entry' in changed:
        author_can_delete_entry = r('author_can_delete_entry')
        context.setDelEntryAuthorAllowed( author_can_delete_entry )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'author_can_delete_entry', author_can_delete_entry, force=1 )
    if 'no_gaps' in changed:
        no_gaps = r('no_gaps')
        context.setNoGaps( no_gaps )
        portal_log( context, 'registry_options', 'changed by %s' % username, 'no_gaps', no_gaps, force=1 )
    if 'last_id' in changed:
        context.setInternalCounter( last_id )

    message = ""
    if REQUEST is not None:
        if r('add_field'):
            fname = r('fname')
            ftitle = r('ftitle')
            ftype = r('ftype')
            fedit = r('fedit')
            system_field = r('system_field')
            context.addColumn( id = fname
                             , title = ftitle
                             , typ = ftype
                             , editable = fedit
                             , system_field = system_field
                             )
            message = "Field added"
            portal_log( context, 'registry_options', 'changed by %s' % username, 'add_field', fname, force=1 )
        elif r('del_fields'):
            ids=r('selected_fields') or []
            for id in ids:
                context.delColumn(id)
                portal_log( context, 'registry_options', 'changed by %s' % username, 'del_field', id, force=1 )
            if ids:
                message = "Field removed"
        else:
            if not context.listColumns():
                message = "You have to specify at least one report field"
            else:
                message = "Changes saved"

    REQUEST['RESPONSE'].redirect(context.absolute_url(action='registry_options_form', message=message))
else:
    REQUEST['RESPONSE'].redirect(context.absolute_url(action='registry_options_form'))