from typing import List, Dict
from langchain_core.messages import HumanMessage
from datetime import datetime
from utils import Interval, save_graph_as_png, parse_str_to_json
from .workflow import Workflow


class Agent:

    @staticmethod
    def run(
            primary_interval: Interval,
            intervals: List[Interval],
            tickers: List[str],
            end_date: datetime,
            portfolio: Dict,
            strategies: List[str],
            show_reasoning: bool = False,
            show_agent_graph: bool = False,
            model_name: str = "gpt-4o",
            model_provider: str = "OpenAI"
    ):
        """
        Executes the trading workflow using the specified configuration.
        Parameters:
            primary_interval (Interval): The primary time interval used for decision making.
            intervals (List[Interval]): List of all time intervals to process data for.
            tickers (List[str]): List of asset symbols to include in the backtest or live run.
            end_date (str): The end date for historical data used in the workflow.
            portfolio (Dict): The initial state of the portfolio, including cash, positions, and margins.
            strategies (List[str]): List of trading strategies to include in the workflow.
            show_reasoning (bool, optional): If True, includes model reasoning in the output. Defaults to False.
            show_agent_graph (bool, optional): If True, saves and displays the graph of the agent workflow. Defaults to False.
            model_name (str, optional): The name of the LLM model to use. Defaults to "gpt-4o".
            model_provider (str, optional): The provider of the LLM model. Defaults to "OpenAI".

        Returns:
        None
        """
        # Create a new workflow if analysts are customized
        workflow = Workflow.create_workflow(intervals=intervals, strategies=strategies)
        agent = workflow.compile()

        if show_agent_graph:
            file_path = ""
            for strategy_name in strategies:
                file_path += strategy_name + "_"
                file_path += "graph.png"
            # save_graph_as_png(agent, file_path)

        final_state = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "primary_interval": primary_interval,
                    "intervals": intervals,
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                },
            },
        )
        # print("the final state:", final_state["data"]["analyst_signals"])
        return {
            "decisions": parse_str_to_json(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
