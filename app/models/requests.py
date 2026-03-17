from pydantic import BaseModel, field_validator


class ChatRequest(BaseModel):
    message: str
    sender: str = "unknown"
    session_id: str = "default"

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be empty")
        return value


class WebhookMessage(BaseModel):
    content: str
    sender_name: str | None = None
    sender_id: str | None = None
    sender_is_agent: bool = False
    conversation_id: str | None = None


class WebhookConversation(BaseModel):
    id: str | None = None


class WebhookRequest(BaseModel):
    event: str | None = None
    message: WebhookMessage
    conversation: WebhookConversation | None = None
