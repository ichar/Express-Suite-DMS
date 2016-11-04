## Script (Python) "aboveInThread"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=top_action='view',ext_params=None
##title=Discussion parent breadcrumbs
##
breadcrumbs = ''
ext_params = ext_params and '?%s' % ext_params or ''

if hasattr(context, 'parentsInThread'):
   parents = context.parentsInThread()
else:
   parents = None

if parents:
    for parent in parents:
        isTaskItem = parent.implements('isTaskItem')
        if isTaskItem and parent.validate() or not isTaskItem:
            p_str = '<a target="workfield" href="%s/%s%s">%s</a> - ' % ( \
                parent.absolute_url(), 
                breadcrumbs and 'view' or top_action, 
                ext_params,
                parent.Title() or parent.Description()
            )
            breadcrumbs = breadcrumbs + p_str

p_str = '%s' % ( context.Title() or context.Description() )
breadcrumbs = breadcrumbs + p_str

return breadcrumbs