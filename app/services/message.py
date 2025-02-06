from datetime import UTC, datetime

from models.message import Message
from neo4j import ManagedTransaction


class MessageService:
    def _send_message(self, tx: ManagedTransaction, message: Message):
        # Handle private accounts and blocked accounts
        query = """
        MATCH (sender:User {user_id: $sender_id})
        MATCH (receiver:User {user_id: $receiver_id})
        
        // Check for any blocking relationships in either direction
        OPTIONAL MATCH (sender)-[b1:BLOCKS]->(receiver)
        OPTIONAL MATCH (receiver)-[b2:BLOCKS]->(sender)

        // For private accounts, check if sender follows receiver
        OPTIONAL MATCH (sender)-[follows:FOLLOWS]->(receiver)
        
        WITH sender, receiver, b1, b2, follows, receiver.is_private as is_private
        WHERE b1 IS NULL AND b2 IS NULL
        AND (
            NOT is_private
            OR (is_private AND follows IS NOT NULL)
        )
        // If this is a reply, match the original message
        OPTIONAL MATCH (original_msg:Message {message_id: $reply_to_message_id})
        WHERE $reply_to_message_id IS NOT NULL

        // If sharing a post, match it
        OPTIONAL MATCH (post:Post {post_id: $shared_post_id})
        WHERE $shared_post_id IS NOT NULL

        // Create the message
        CREATE (msg:Message {
            message_id: $message_id,
            content: $content,
            created_at: $current_time,
            is_deleted: false
        })

        // Create the core relationships
        CREATE (sender)-[sent:SENT]->(msg)-[received:RECEIVED_BY]->(receiver)

        // Handle replies and shared posts
        FOREACH (ignored IN CASE WHEN original_msg IS NOT NULL THEN [1] ELSE [] END |
            CREATE (msg)-[reply:REPLIES_TO]->(original_msg)
        )
        FOREACH (ignored IN CASE WHEN post IS NOT NULL THEN [1] ELSE [] END |
            CREATE (msg)-[shares:SHARES]->(post)   
        )
        RETURN {
            success:true,
            message: msg,
            sender: sender,
            receiver: receiver
        } as result
        """
        result = tx.run(
            query,
            message_id=str(message.message_id),
            sender_id=str(message.sender_id),
            receiver_id=str(message.receiver_id),
            content=message.content,
            reply_to_message_id=(
                str(message.reply_to_message_id)
                if message.reply_to_message_id
                else None
            ),
            shared_post_id=(
                str(message.shared_post_id) if message.shared_post_id else None
            ),
            current_time=datetime.now(UTC),
        )
        if record := result.single():
            return Message(**record["result"]["message"])
        else:
            # If we didn't get a result, let's find out why
            check_query = """
            MATCH (sender:User {user_id: $sender_id})
            MATCH (receiver:User {user_id: $receiver_id})
            OPTIONAL MATCH (sender)-[b1:BLOCKS]->(receiver)
            OPTIONAL MATCH (receiver)-[b2:BLOCKS]->(sender)
            OPTIONAL MATCH (sender)-[follows:FOLLOWS]->(receiver)
            RETURN {
                sender_blocked_receiver: b1 IS NOT NULL,
                receiver_blocked_sender: b2 IS NOT NULL,
                is_private: receiver.is_private,
                sender_follows_receiver: follows IS NOT NULL
            } as status
            """
            status = tx.run(
                check_query,
                sender_id=str(message.sender_id),
                receiver_id=str(message.receiver_id),
            )
            if status_data := status.single():
                status = status_data["status"]
                if status["sender_blocked_receiver"]:
                    raise ValueError("Cannot send message to a user you have blocked")
                elif status["receiver_blocker_sender"]:
                    raise ValueError(
                        "Cannot send message to a user who has blocked you"
                    )
                elif status["is_private"] and not status["sender_follows_receiver"]:
                    raise ValueError(
                        "Cannot send message to a private account you don't follow"
                    )
            else:
                raise ValueError("One or both users not found")
