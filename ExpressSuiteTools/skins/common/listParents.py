## Script (Python) "listParents"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=
##
parents = []
parent  = context

while not parent.implements('isPortalRoot'):
    if parent.meta_type == 'Publisher Entry Point':
	parents += parent.getParents()
    elif parent.implements('isPrincipiaFolderish'):
	parents.insert( 0, parent )
    parent = parent.aq_parent

# exclude storage from the list
return parents[1:]
