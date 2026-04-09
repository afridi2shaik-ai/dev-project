from pydantic import Field

from .base_schema import BaseSchema


class OfferRequest(BaseSchema):
    pc_id: str | None = Field(None, description="The peer connection ID.")
    sdp: str = Field(..., description="The SDP offer from the client.")
    type: str = Field(..., description="The type of the SDP offer.")
    restart_pc: bool = Field(False, description="Flag to indicate if the peer connection should be restarted.")
    session_id: str | None = Field(None, description="The session ID to associate with this connection.")
    # This schema doesn't have assistant_overrides, which is correct.
    # The overrides are handled during the /api/sessions call that happens before this.
    # So no changes are needed here.


class OfferResponse(BaseSchema):
    pc_id: str = Field(..., description="The peer connection ID for the session.")
    sdp: str = Field(..., description="The SDP answer from the server.")
    type: str = Field(..., description="The type of the SDP answer.")
    session_id: str = Field(..., description="The session ID of the session.")
