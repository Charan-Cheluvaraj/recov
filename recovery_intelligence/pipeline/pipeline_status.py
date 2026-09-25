from enum import Enum

class PipelineStage(str, Enum):
    EVIDENCE_HASHING = "evidence_hashing"
    FILE_CARVING = "file_carving"
    FRAGMENT_ANALYSIS = "fragment_analysis"
    FINGERPRINTING = "fingerprinting"
    RELATIONSHIP_DETECTION = "relationship_detection"
    CLUSTERING = "clustering"
    RECONSTRUCTION = "reconstruction"
    STRUCTURAL_VALIDATION = "structural_validation"
    FOUR_SIGNAL_SCORING = "four_signal_scoring"
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"
    PRIORITY_RANKING = "priority_ranking"
    LLM_NARRATIVE_GENERATION = "llm_narrative_generation"
    RESULT_PERSISTENCE = "result_persistence"
    EVALUATION = "evaluation"
    COMPLETED = "completed"
    FAILED = "failed"

class PipelineStatus:
    def __init__(self):
        self.current_stage: PipelineStage = PipelineStage.EVIDENCE_HASHING
        self.progress_percentage: float = 0.0
        self.message: str = "Pipeline initialized"
        self.errors: list = []

    def update(self, stage: PipelineStage, progress: float, message: str = ""):
        self.current_stage = stage
        self.progress_percentage = progress
        self.message = message or f"Running {stage.value}"
