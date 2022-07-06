
export enum NotificationType {
    AuctionEnd = 'AUCTION_END',
    AuctionEnd10Min = 'AUCTION_END_10MIN',
    NewBid = 'NEW_BID',
}

export enum NotificationAction {
    None = 'NONE',
    TwitterDM = 'TWITTER_DM',
}

export interface UserNotification {
    notificationType: NotificationType;
    notificationTypeDescription: string;
    action: NotificationAction;
    actionDescription: string;
}

export function fromJson(json: any) {
    return {
        notificationType: <NotificationType>json.notification_type,
        notificationTypeDescription: <string>json.notification_type_description,
        action: <NotificationAction>json.action,
        actionDescription: <string>json.action_description,
    }
}

export class PostUserNotification {
    notificationType: NotificationType;
    action: NotificationAction;

    public constructor(notificationType: NotificationType, action: NotificationAction) {
        this.notificationType = notificationType;
        this.action = action;
    }

    public toJson() {
        return JSON.stringify({
            notification_type: <string>this.notificationType,
            action: <string>this.action,
        });
    }
}