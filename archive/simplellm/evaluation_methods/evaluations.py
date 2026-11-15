from simplellm.evaluation_methods.tools import graph_gen
import logging
logger = logging.getLogger(__name__)
def run(root_dir):
    try:
        graph_gen.run(root_dir)
    except Exception as e:
        logger.info(f"Global analysis failed: {e}")