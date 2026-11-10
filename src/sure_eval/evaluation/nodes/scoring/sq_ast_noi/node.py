from sure_eval.evaluation.nodes.scoring._sq_ast_node import run_node, score_sq_ast

NODE_ID = "scoring/sq_ast_noi"
NODE_VERSION = "v1"


def score_sq_ast_noi(rows, *, provider):
    return score_sq_ast(rows, provider=provider, dimension="noi", node_id=NODE_ID)


def main(argv=None):
    return run_node(argv, dimension="noi", node_id=NODE_ID)


if __name__ == "__main__":
    raise SystemExit(main())
