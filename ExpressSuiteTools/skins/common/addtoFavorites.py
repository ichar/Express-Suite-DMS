## Script (Python) "addtoFavorites"
##title=Add item to favourites
##parameters=
from Products.ExpressSuiteTools.SecureImports import refreshClientFrame

favorites = context.portal_membership.getPersonalFolder( 'favorites', create=1 )

if not favorites:
    message='Unable to create Favorites folder'
else:
    uid = context.getUid()
    x, obs = favorites.listObjects() #  path_idx='parent_path' 
    for shortcut in obs:
        try:
            ob = x.getObject().getObject()
        except:
            continue
        if ob is not None and uid == ob.getUid():
            message='Shortcut already exists'
            action = context.getTypeInfo().getActionById('view','')
            url = context.absolute_url(redirect=1, action=action, frame='inFrame', message=message)
            return context.REQUEST['RESPONSE'].redirect(url, status=303)

    new_id = 'fav_' + str(int( context.ZopeTime()))
    favorites.manage_addProduct['ExpressSuiteTools'].addShortcut( id=new_id, remote=context )
    refreshClientFrame('favorites')
    message='Document was added to the favorites'

action = context.getTypeInfo().getActionById('view','')
url = context.absolute_url(redirect=1, action=action, message=message) #, frame='inFrame'
return context.REQUEST['RESPONSE'].redirect(url, status=303)
