## Script (Python) "document_link_add"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=destination_uid=None, relation=0, ver_id=None
##title=
##
REQUEST = context.REQUEST
report_url = REQUEST.get('report_url', None)

if report_url:
    if not REQUEST.get('add_report_to_links') or destination_uid is None:
        return REQUEST.RESPONSE.redirect(
            context.absolute_url( redirect=1, action='document_follow_up_form', frame='document_frame' )
            )
    ver_id = None
    relation = 2

base = context
while not ( base.implements('isVersion') or base.implements('isDocument') ):
    base = base.aq_parent

source_uid = base.getUid()
source_ver_id = ( base.implements('isVersion') or base.implements('isVersionable') ) and base.getCurrentVersionId()

try:
    link = context.portal_links.createLink( source_uid=source_uid, destination_uid=destination_uid, source_ver_id=source_ver_id,
            destination_ver_id=ver_id, relation=relation, REQUEST=REQUEST )
except:
    link = None

if report_url:
    message = "Report was added to document links"
    return REQUEST.RESPONSE.redirect(
            base.getVersion().absolute_url( redirect=1, action='document_attaches', frame='document_frame', message=message ),
            status=303 )

return link
