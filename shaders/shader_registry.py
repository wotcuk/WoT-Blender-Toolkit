from . import pbs_tank
from . import lightonly

SHADER_SCRIPT_MAP = {
    "pbs_tank": pbs_tank,
    "pbs_tank_skinned": pbs_tank,
    "pbs_ext": pbs_tank, 
    
    "lightonly": lightonly,
    "lightonly_skinned": lightonly,
    "vector_animation": lightonly, 
    "vector_animation_2.fx": lightonly
}