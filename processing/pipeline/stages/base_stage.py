from abc import ABC, abstractmethod

from ..asset_context import AssetProcessingContext


class ProcessingStage(ABC):
    """
    Abstract base class for a stage in the asset processing pipeline.
    """

    @abstractmethod
    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Executes the processing logic of this stage.

        Args:
            context: The current asset processing context.

        Returns:
            The updated asset processing context.
        """
        pass