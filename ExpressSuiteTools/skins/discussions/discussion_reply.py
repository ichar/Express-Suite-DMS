## Script (Python) "discussion_reply"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=title, text, Creator, version=None, fullname=None, email=None, status=1, last_comment=1, is_notify=None, users=None
##title=Reply to content
##
from Products.CMFCore.utils import getToolByName
from Products.ExpressSuiteTools.SecureImports import CommitThread

REQUEST = context.REQUEST

doc_ver = REQUEST.get('doc_ver')
IsReplyTo = hasattr( context, 'inReplyTo' ) and 1 or 0

try:
    replyID = context.createReply( title=title, text=text, Creator=Creator, version=doc_ver, email=email )
    reply = context.restrictedTraverse( replyID )
    IsError = 0
except:
    IsError = 1

if not IsError:
    try:
        reply.editMetadata( description=title, contributors=(fullname, ) )
    except:
        pass

    REQUEST.RESPONSE.setCookie('fullname', fullname, path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')
    REQUEST.RESPONSE.setCookie('email', email, path='/', expires='Wed, 19 Feb 2020 14:28:00 GMT')

    lang = REQUEST.get('LOCALIZER_LANGUAGE')
    mailhost = context.MailHost

    comment_link = reply.absolute_url() + '?expand=1'
    comment_title = title # context.Title()
    comment_autor = reply.Creator()

    base = context
    while not base.implements('isDocument'):
        base = base.aq_parent #getVersionable()
        if base.implements('isContentStorage') or base.implements('isPortalRoot'):
            base = None
            break

    document_title = base is not None and base.Title() or context.Title()

    if IsReplyTo:
        reply.setNotifiedUsers()
    message = None

CommitThread( context, 'discussion_reply', IsError )

if not IsError and is_notify and users:
    try:
        count = mailhost.sendTemplate( template='discussion.notify_user' \
                , mto=users
                , mfrom=reply.Creator()
                , lang=lang
                , from_member=1
                , comment_autor=comment_autor
                , comment_text=text
                , comment_link=comment_link
                , comment_title=comment_title
                , title=document_title
            )
    except:
        count = 0
    if count:
        reply.setNotifiedUsers( users )
        message = "Disscusion message was sent successfully. Total: $ %s" % str(count)
    else:
        message = "Disscusion message was no sent $ $ error"

if not IsReplyTo:
    REQUEST.RESPONSE.redirect( context.aq_parent.absolute_url( action='document_comments', message=message, frame='document_frame' ))
else:
    REQUEST.RESPONSE.redirect( context.aq_parent.absolute_url( message=message ))
