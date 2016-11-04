## Script (Python) "listThreads"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=show=None,filter=None,filter_ver=None,parent_reply=None
##

def getAllReplies(parent_rep):
    replies = context.branches(show=show, filter=filter, filter_ver=filter_ver, parent_reply=parent_rep)
    for rep in replies[:]:
        replies.extend(getAllReplies(rep.talkback))
    return replies

return getAllReplies(context.implements('isVersion') and context.aq_parent.talkback or context.talkback)
