"""
Quality evaluation runner - orchestrates test execution and prompt refinement.
Runs test cases, evaluates answers, detects failures, refines prompts, and iterates.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests

from answer_verifier import AnswerVerifier, evaluate_batch
from prompt_refinement import PromptRefinementEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Orchestrate quality evaluation and prompt refinement."""
    
    def __init__(
        self,
        test_cases_file: str,
        api_base_url: str = "http://localhost:8001/api",
        llm_api_url: str = "http://localhost:8080/prompt",
        max_iterations: int = 5,
        improvement_threshold: float = 0.05,
    ):
        """
        Initialize the evaluation runner.
        
        Args:
            test_cases_file: Path to JSON file with test cases
            api_base_url: Base URL of the RAG API
            llm_api_url: URL of the LLM API
            max_iterations: Maximum refinement iterations
            improvement_threshold: Minimum improvement to continue iterating
        """
        self.test_cases_file = test_cases_file
        self.api_base_url = api_base_url
        self.llm_api_url = llm_api_url
        self.max_iterations = max_iterations
        self.improvement_threshold = improvement_threshold
        
        self.test_cases = self._load_test_cases()
        self.prompt_engine = PromptRefinementEngine()
        self.verifier = AnswerVerifier()
        
        self.evaluation_history = []
    
    def _load_test_cases(self) -> List[Dict[str, Any]]:
        """Load test cases from JSON file."""
        try:
            with open(self.test_cases_file, 'r') as f:
                data = json.load(f)
            test_cases = data.get("test_cases", [])
            logger.info(f"Loaded {len(test_cases)} test cases from {self.test_cases_file}")
            return test_cases
        except FileNotFoundError:
            logger.error(f"Test cases file not found: {self.test_cases_file}")
            return []
    
    def run_single_evaluation(self, iteration_number: int = 0) -> Dict[str, Any]:
        """
        Run evaluation on all test cases with current prompt.
        
        Returns:
            Batch evaluation results
        """
        if not self.test_cases:
            logger.error("No test cases loaded")
            return {}
        
        logger.info(f"\n{'='*80}")
        logger.info(f"EVALUATION ITERATION {iteration_number}")
        logger.info(f"{'='*80}")
        
        # Get current prompt
        current_prompt = self.prompt_engine.get_current_prompt()
        
        queries = []
        answers = []
        retrieved_chunks_list = []
        
        # Run each test case through the query pipeline
        for i, test_case in enumerate(self.test_cases):
            query = test_case["query"]
            queries.append(query)
            
            logger.info(f"\n[{i+1}/{len(self.test_cases)}] Query: {query[:80]}...")
            
            try:
                # Call RAG API
                response = requests.post(
                    f"{self.api_base_url}/query",
                    json={"query": query, "top_k": 3},
                    timeout=30,
                )
                
                if response.status_code != 200:
                    logger.error(f"API returned {response.status_code}")
                    answers.append("API Error")
                    retrieved_chunks_list.append([])
                    continue
                
                result = response.json()
                answer = result.get("answer", "")
                context_chunks = result.get("context_chunks", [])
                
                # Log answer
                logger.info(f"Generated answer: {answer[:100]}...")
                
                answers.append(answer)
                retrieved_chunks_list.append(context_chunks)
                
            except Exception as e:
                logger.error(f"Error querying API: {e}")
                answers.append(f"Error: {str(e)}")
                retrieved_chunks_list.append([])
        
        # Evaluate all answers
        logger.info(f"\n{'='*80}")
        logger.info("EVALUATING ANSWERS")
        logger.info(f"{'='*80}")
        
        batch_results = evaluate_batch(
            test_cases=self.test_cases,
            queries=queries,
            answers=answers,
            retrieved_chunks_list=retrieved_chunks_list,
        )
        
        # Add iteration metadata
        batch_results["iteration_number"] = iteration_number
        batch_results["current_prompt"] = current_prompt
        
        # Log summary
        logger.info(f"\nPass rate: {batch_results['pass_rate']:.1%}")
        logger.info(f"Critical failures: {batch_results['critical_failures']}")
        logger.info(f"Average quality score: {batch_results['average_final_quality_score']:.4f}")
        
        self.evaluation_history.append(batch_results)
        
        return batch_results
    
    def run_iterative_evaluation(self) -> Dict[str, Any]:
        """
        Run evaluation with iterative prompt refinement.
        
        Returns:
            Final evaluation results and history
        """
        logger.info(f"\n{'#'*80}")
        logger.info("STARTING ITERATIVE EVALUATION PROCESS")
        logger.info(f"{'#'*80}")
        logger.info(f"Test cases: {len(self.test_cases)}")
        logger.info(f"Max iterations: {self.max_iterations}")
        logger.info(f"Improvement threshold: {self.improvement_threshold}")
        
        previous_results = None
        no_improvement_count = 0
        
        for iteration in range(self.max_iterations):
            # Run evaluation
            current_results = self.run_single_evaluation(iteration_number=iteration)
            
            if not current_results:
                logger.error("Evaluation failed")
                break
            
            # Check if all tests pass
            if current_results["pass_rate"] >= 1.0:
                logger.info("\n✓ ALL TESTS PASSED!")
                break
            
            # Check if we should continue iterating
            if iteration < self.max_iterations - 1:
                # Refine prompt for next iteration
                refined_prompt, iteration_record = self.prompt_engine.refine_prompt(
                    previous_results=previous_results,
                    current_results=current_results,
                    iteration_number=iteration,
                )
                
                logger.info(f"\n{'='*80}")
                logger.info("PROMPT REFINEMENT")
                logger.info(f"{'='*80}")
                logger.info(f"Reason: {iteration_record.reason_for_change}")
                logger.info(f"Improvement: {iteration_record.improvement:.4f}")
                
                if iteration_record.improvement < self.improvement_threshold:
                    no_improvement_count += 1
                    logger.warning(f"No significant improvement ({no_improvement_count}/2)")
                    if no_improvement_count >= 2:
                        logger.info("Stopping - no meaningful improvement in last 2 iterations")
                        break
                else:
                    no_improvement_count = 0
            
            previous_results = current_results
        
        # Generate final report
        final_report = self._generate_final_report()
        
        return final_report
    
    def _generate_final_report(self) -> Dict[str, Any]:
        """Generate a comprehensive final report."""
        if not self.evaluation_history:
            return {}
        
        # Get final iteration results
        final_results = self.evaluation_history[-1]
        
        # Calculate overall progress
        initial_pass_rate = self.evaluation_history[0]["pass_rate"]
        final_pass_rate = final_results["pass_rate"]
        pass_rate_improvement = final_pass_rate - initial_pass_rate
        
        initial_critical = self.evaluation_history[0]["critical_failures"]
        final_critical = final_results["critical_failures"]
        critical_improvement = initial_critical - final_critical
        
        initial_quality = self.evaluation_history[0]["average_final_quality_score"]
        final_quality = final_results["average_final_quality_score"]
        quality_improvement = final_quality - initial_quality
        
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "test_case_count": len(self.test_cases),
            "total_iterations": len(self.evaluation_history),
            "initial_state": {
                "pass_rate": round(initial_pass_rate, 4),
                "critical_failures": initial_critical,
                "average_quality_score": round(initial_quality, 4),
            },
            "final_state": {
                "pass_rate": round(final_pass_rate, 4),
                "critical_failures": final_critical,
                "average_quality_score": round(final_quality, 4),
            },
            "improvements": {
                "pass_rate_improvement": round(pass_rate_improvement, 4),
                "critical_failures_reduced": critical_improvement,
                "quality_improvement": round(quality_improvement, 4),
            },
            "evaluation_history": self.evaluation_history,
            "prompt_iteration_history": self.prompt_engine.get_iteration_history(),
            "final_prompt": self.prompt_engine.get_current_prompt(),
        }
        
        return report
    
    def save_report(self, output_file: str) -> None:
        """Save final report to JSON file."""
        report = self._generate_final_report()
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\nReport saved to {output_file}")
    
    def print_summary(self) -> None:
        """Print human-readable summary of evaluation results."""
        if not self.evaluation_history:
            print("No evaluation results")
            return
        
        print(f"\n{'='*80}")
        print("EVALUATION SUMMARY")
        print(f"{'='*80}\n")
        
        # Initial state
        initial = self.evaluation_history[0]
        print(f"Initial State (Iteration 0):")
        print(f"  Pass rate: {initial['pass_rate']:.1%} ({initial['passed_cases']}/{initial['total_cases']})")
        print(f"  Critical failures: {initial['critical_failures']}")
        print(f"  Avg quality score: {initial['average_final_quality_score']:.4f}\n")
        
        # Final state
        final = self.evaluation_history[-1]
        print(f"Final State (Iteration {len(self.evaluation_history)-1}):")
        print(f"  Pass rate: {final['pass_rate']:.1%} ({final['passed_cases']}/{final['total_cases']})")
        print(f"  Critical failures: {final['critical_failures']}")
        print(f"  Avg quality score: {final['average_final_quality_score']:.4f}\n")
        
        # Improvements
        print(f"Improvements:")
        print(f"  Pass rate: {(final['pass_rate'] - initial['pass_rate'])*100:+.1f}%")
        print(f"  Critical failures: {initial['critical_failures'] - final['critical_failures']:+d}")
        print(f"  Quality score: {(final['average_final_quality_score'] - initial['average_final_quality_score']):+.4f}\n")
        
        # Test case results
        print(f"Final Test Results:")
        for i, test_result in enumerate(final.get("test_results", []), 1):
            status = "[PASS]" if test_result["overall_pass"] else "[FAIL]"
            print(f"  [{i}] {test_result['test_case_id']}: {status}")
            if not test_result["overall_pass"] and test_result.get("failure_reasons"):
                for reason in test_result["failure_reasons"][:2]:
                    print(f"      - {reason}")
        
        print(f"\n{'='*80}\n")


def main():
    """Main entry point for evaluation."""
    runner = EvaluationRunner(
        test_cases_file="evaluation_test_cases.json",
        api_base_url="http://localhost:8001/api",
        llm_api_url="http://localhost:8080/prompt",
        max_iterations=5,
        improvement_threshold=0.05,
    )
    
    # Run iterative evaluation
    final_report = runner.run_iterative_evaluation()
    
    # Save report
    runner.save_report("evaluation_report_final.json")
    
    # Print summary
    runner.print_summary()


if __name__ == "__main__":
    main()
