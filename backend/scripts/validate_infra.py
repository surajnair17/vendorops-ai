"""Optional cfn-lint entry point for platforms where executable wrappers are unavailable."""

import sys


def main():
    try:
        from cfnlint.runner import main as lint
    except ImportError as error:
        raise SystemExit(
            "Install backend/infra/requirements.txt to validate CloudFormation."
        ) from error
    sys.argv = ["cfn-lint", "backend/infra/cloudformation.yaml", *sys.argv[1:]]
    lint()


if __name__ == "__main__":
    main()
