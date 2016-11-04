## Script (Python) "get_icon"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=
##
from Products.ExpressSuiteTools.SecureImports import departmentDictionary

meta_type = context.meta_type
icon = None

if meta_type == 'Heading':
    if departmentDictionary.IsDepartmentFolder( context, context.relative_url() ):
        return 'department_icon.gif'
if meta_type in ['File Attachment','FS File'] or context.implements('isFileAttachment'):
    return context.getIcon()
elif meta_type == 'Task Item':
    state = context.getTaskState()
    if state:
        icon = 'task.gif'
        task_is_automated = getattr( context, 'task_is_automated', None )
        if task_is_automated:
            icon = '%s_%s' % ( 'green', icon )
        else:
            base = context.getBase()
            IsPortalRoot = base is not None and base.implements('isPortalRoot') and 1 or 0
            icon = '%s_%s' % ( IsPortalRoot and 'blue' or 'red', icon )
else:
    state = context.portal_workflow.getInfoFor( context, 'state', '' )

if meta_type in ['HTMLDocument'] and state not in ['evolutive','OnWork'] and \
   not getattr( context, 'registry_data', None ):
    return 'doc_icon_unregistered.gif'

if not icon:
    x = hasattr( context, 'getIcon' ) and context.getIcon(1)
    icon = x or getattr( context, 'icon', None )

if icon:    
    ext = icon[-4:]
    postfix = ( meta_type == 'Shortcut' and '_shortcut' ) or ( state and '_'+state ) or ''
    state_icon = icon.replace(icon[-4:], "%s%s" % ( postfix, ext ))
else:
    state_icon = None

if state_icon and hasattr( context, state_icon ):
    return state_icon
else:
    return icon
