from sure_eval.evaluation.nodes.scoring._sq_ast_node import run_node, score_sq_ast

NODE_ID = "scoring/sq_ast_mos"
NODE_VERSION = "v1"


def score_sq_ast_mos(rows, *, provider):
    return score_sq_ast(rows, provider=provider, dimension="mos", node_id=NODE_ID)


def main(argv=None):
    return run_node(argv, dimension="mos", node_id=NODE_ID)


if __name__ == "__main__":
    raise SystemExit(main())
