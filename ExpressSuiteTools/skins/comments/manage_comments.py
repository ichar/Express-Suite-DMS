## Script (Python) "mamage_comments"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST
##title=
##
# $Id: manage_comments.py,v 1.2 2003/08/12 16:36:59 Exp $
# $Revision: 1.2 $

REQUEST = context.REQUEST
comments = context.portal_comments

if REQUEST.has_key('add_context'):
    context_type = REQUEST['new_context_type'].strip()
    comments.addContext( context_type )

elif REQUEST.has_key('del_context'):
    context_type = REQUEST.get('del_context_type')
    comments.delContext( context_type )

elif REQUEST.has_key('add_comment'):
    context_type = REQUEST['context_type'].strip()
    try: id = REQUEST['id'].strip()
    except: id = None
    title = REQUEST['title'].strip()
    description = REQUEST['description'].strip()
    comments.addComment( context_type, id, title, description, REQUEST )

elif REQUEST.has_key('remove'):
    for id in REQUEST['ids']:
        comments.deleteComment( id )

elif REQUEST.has_key('save'):
    id = REQUEST.get('id')
    context.editComment( id, REQUEST )

return comments.redirect( action='manageComments', REQUEST=REQUEST )
