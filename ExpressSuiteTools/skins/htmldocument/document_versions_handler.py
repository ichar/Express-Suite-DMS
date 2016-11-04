## Script (Python) "document_versions_handler"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST
##title=Handle document versions
##

if REQUEST.get('action_name') == 'create_version':
    return context.version_create_form( context, REQUEST )

elif REQUEST.get('action_name') == 'compare_versions':
    original = context.getVersion( REQUEST['ver_id_for_compare'] )
    revised = context.getVersion( REQUEST['ver_id'] )
    result = revised.getChangesFrom( original )

    return context.document_compare_results( context, REQUEST, result=result, original=original, revised=revised )

return context.redirect( action='document_versions_form' )
