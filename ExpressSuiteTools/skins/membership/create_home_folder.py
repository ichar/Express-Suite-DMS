## Script (Python) "create_home_folder"
##bind container=container
##bind context=context
##bind namespace=_
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST=None, userid=None
##title=Create Home Folder Handler
##
REQUEST = context.REQUEST
portal = context.portal_url.getPortalObject()
user = context.portal_membership.getAuthenticatedMember()
registered_by_user = user.getUserName()

if userid is not None:
    member = context.portal_membership.getMemberById( userid )
else:
    member = user

if member is not None:
    username = member.getUserName()
    home = member.getHomeFolder( create=1 )

    if home is not None:
        members = portal.storage.members
        ids = members.user_defaults.objectIds()
        if ids:
            data = members.user_defaults.manage_copyObjects( ids )
            home.manage_pasteObjects( data )
            if username:
                home.changeOwnership( username, recursive=1 )

    if home is not None and registered_by_user:
        res = context.portal_catalog.searchResults( path=home.physical_path(), implements='isContentStorage' )
        for r in res:
            ob = r.getObject()
            if ob is None:
                continue
            ob.delLocalRoles( userids=[ registered_by_user ] )
    
qs = '/personalize_form?portal_status_message=Home+folder+created.'

abc = REQUEST.get('abc', None)
department = REQUEST.get('dep', None)

if userid:
    qs += '&userid=%s' % userid
if abc:
    qs += '&abc=%s' % abc
if department:
    qs += '&dep=%s' % department

context.REQUEST.RESPONSE.redirect( context.portal_url() + qs )
