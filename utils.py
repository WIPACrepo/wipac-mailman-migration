def get_google_group_config_from_mailman_config(mmcfg):
    # https://developers.google.com/admin-sdk/groups-settings/v1/reference/groups#json
    if mmcfg["advertised"] and mmcfg["archive"]:
        if mmcfg["archive_private"]:
            who_can_view_group = "ALL_MEMBERS_CAN_VIEW"
        else:
            who_can_view_group = "ALL_IN_DOMAIN_CAN_VIEW"
    else:  # not advertised or not archived
        who_can_view_group = "ALL_MANAGERS_CAN_VIEW"

    if mmcfg["generic_nonmember_action"] in (0, 1):  # accept, hold
        who_can_post_message = "ANYONE_CAN_POST"
    else:  # reject, discard
        who_can_post_message = "ALL_MEMBERS_CAN_POST"
    if mmcfg["default_member_moderation"] and mmcfg["member_moderation_action"] in (
        1,
        2,
    ):  # reject or discard
        who_can_post_message = "NONE_CAN_POST"

    if mmcfg["generic_nonmember_action"] == 0:  # accept
        message_moderation_level = "MODERATE_NONE"
    else:  # hold, reject, discard
        message_moderation_level = "MODERATE_NON_MEMBERS"
    if mmcfg["default_member_moderation"]:
        message_moderation_level = "MODERATE_ALL_MESSAGES"

    if mmcfg["private_roster"] == 0:
        who_can_view_membership = "ALL_IN_DOMAIN_CAN_VIEW"
    elif mmcfg["private_roster"] == 1:
        who_can_view_membership = "ALL_MEMBERS_CAN_VIEW"
    else:
        who_can_view_membership = "ALL_MANAGERS_CAN_VIEW"

    ggcfg = {
        "email": mmcfg["email"],
        "name": mmcfg["real_name"],
        "description": (
            mmcfg["description"] + "\n" + mmcfg["info"] if mmcfg["info"] else mmcfg["description"]
        ),
        "whoCanJoin": "CAN_REQUEST_TO_JOIN",
        "whoCanViewMembership": who_can_view_membership,
        "whoCanViewGroup": who_can_view_group,
        "allowExternalMembers": "true",  # can't be tighter until we start forcing people to use @iwe addresses
        "whoCanPostMessage": who_can_post_message,
        "allowWebPosting": "true",
        "primaryLanguage": "en",
        "isArchived": ("true" if mmcfg["archive"] else "false"),
        "archiveOnly": "false",
        "messageModerationLevel": message_moderation_level,
        "spamModerationLevel": "MODERATE",  # this is the default
        "replyTo": "REPLY_TO_IGNORE",  # users individually decide where the message reply is sent
        # "customReplyTo": "",  # only if replyTo is REPLY_TO_CUSTOM
        "includeCustomFooter": "false",
        # "customFooterText": ""  # only if includeCustomFooter,
        "sendMessageDenyNotification": "false",
        # "defaultMessageDenyNotificationText": "",  # only matters if sendMessageDenyNotification is true
        "membersCanPostAsTheGroup": "false",
        "includeInGlobalAddressList": "false",  # has to do with Outlook integration
        "whoCanLeaveGroup": ("ALL_MEMBERS_CAN_LEAVE" if mmcfg["unsubscribe_policy"] else "NONE_CAN_LEAVE"),
        "whoCanContactOwner": "ALL_IN_DOMAIN_CAN_CONTACT",
        "favoriteRepliesOnTop": "false",
        "whoCanApproveMembers": "ALL_MANAGERS_CAN_APPROVE",
        "whoCanBanUsers": "OWNERS_AND_MANAGERS",
        "whoCanModerateMembers": "OWNERS_AND_MANAGERS",
        "whoCanModerateContent": "OWNERS_AND_MANAGERS",
        "whoCanAssistContent": "NONE",  # has something to do with collaborative inbox
        "enableCollaborativeInbox": "false",
        "whoCanDiscoverGroup": (
            "ALL_IN_DOMAIN_CAN_DISCOVER" if mmcfg["advertised"] else "ALL_MEMBERS_CAN_DISCOVER"
        ),
        "defaultSender": "DEFAULT_SELF",
    }
    return ggcfg
