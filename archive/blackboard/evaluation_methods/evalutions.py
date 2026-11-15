from blackboard.evaluation_methods.methods import candidate_test, post_processing_stuff , final_evalutions_signals
import logging
logger = logging.getLogger(__name__)

def run_evaluations(export_dir = ""):
    if export_dir:
        try:
            candidate_test.run(export_dir)
        except Exception as e:
            logger.info(f"Candidate test failed: {e}")
        try:
            post_processing_stuff.run(export_dir)
        except Exception as e:
            logger.info(f"More global test failed (none specified): {e}")
        try:
            final_evalutions_signals.run(export_dir)
        except Exception as e:
            logger.info(f"Final evaluation test failed (none specified): {e}")