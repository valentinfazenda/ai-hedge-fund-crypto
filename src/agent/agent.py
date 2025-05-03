from typing import List, Dict
from langchain_core.messages import HumanMessage

from utils import Interval
from utils.util_func import save_graph_as_png
from .workflow import Workflow


class Agent:

    @staticmethod
    def run(
            intervals: List[Interval],
            tickers: List[str],
            end_date: str,
            portfolio: Dict,
            strategies: List[str],
            primary_interval: Interval = Interval.DAY_1,
            show_reasoning: bool = False,
            show_agent_graph: bool = False,
            model_name: str = "gpt-4o",
            model_provider: str = "OpenAI"
    ):
        """
        :param show_agent_graph:
        :param intervals:
        :param tickers:
        :param end_date:
        :param portfolio:
        :param strategies:
        :param primary_interval:
        :param show_reasoning:
        :param model_name:
        :param model_provider:
        :return:
        """
        # Create a new workflow if analysts are customized
        workflow = Workflow.create_workflow(intervals=intervals, strategies=strategies)
        agent = workflow.compile()

        if show_agent_graph:
            file_path = ""
            for strategy_name in strategies:
                file_path += strategy_name + "_"
                file_path += "graph.png"
            save_graph_as_png(agent, file_path)

        final_state = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
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

        print(final_state)
        # except Exception as e:
        #     print(e.__str__())
        #     pass
        # return {
        #     "decisions": parse_hedge_fund_response(final_state["messages"][-1].content),
        #     "analyst_signals": final_state["data"]["analyst_signals"],
        # }
