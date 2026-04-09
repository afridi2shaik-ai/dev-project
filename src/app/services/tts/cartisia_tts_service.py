# from typing import Any
# from pipecat.services.cartesia.tts import CartesiaTTSService
# from pipecat.transcriptions.language import Language
# from app.core import settings


# def create_tts_service(
#     voice_id: str = "7f423809-0011-4658-ba48-a411f5e516ba",
#     model: str = "sonic-3",
#     language: Any = Language.EN, 
    
# ):
#     return CartesiaTTSService(
#         api_key=settings.CARTESIA_API_KEY,
#         voice_id=voice_id,
#         model=model,
#         language=language,
#     )


from typing import Any, Optional, Optional
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.transcriptions.language import Language
from app.core import settings


def create_tts_service(
    voice_id: str = "7f423809-0011-4658-ba48-a411f5e516ba",
    model: str = "sonic-3",
    language: Any = Language.EN,
    volume: Optional[float] = 1.0,  
    speed: Optional[float] = 1.0,
    emotion: Optional[str] = "neutral"
):
    params = CartesiaTTSService.InputParams(
        language=language,
    
        generation_config=GenerationConfig(
            volume=volume,   # range: 0.5 - 2.0
            speed=speed,     # range: 0.6 - 1.5
            emotion=emotion, # e.g. "neutral", "excited", "sad"
        ),
        
    )

    return CartesiaTTSService(
        api_key=settings.CARTESIA_API_KEY,
        voice_id=voice_id,
        model=model,
        params=params,
    )