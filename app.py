
from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)


class ParseError(Exception):
    pass


# -------------------------------
# Lexer: Convert input into tokens
# -------------------------------

TOKEN_PATTERN = re.compile(
    r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|([+\-*/()=;]))"
)


def tokenize(expression):
    tokens = []
    position = 0

    while position < len(expression):
        if expression[position:].isspace():
            break

        match = TOKEN_PATTERN.match(expression, position)

        if not match:
            bad = position

            while bad < len(expression) and expression[bad].isspace():
                bad += 1

            if bad >= len(expression):
                break

            raise ParseError(
                f"Invalid character at position {bad + 1}: "
                f"'{expression[bad]}'"
            )

        number, identifier, operator = match.groups()

        if number is not None:
            tokens.append({
                "type": "NUMBER",
                "value": number
            })

        elif identifier is not None:
            tokens.append({
                "type": "IDENTIFIER",
                "value": identifier
            })

        else:
            tokens.append({
                "type": "OPERATOR",
                "value": operator
            })

        position = match.end()

    tokens.append({
        "type": "EOF",
        "value": "EOF"
    })

    return tokens


# --------------------------------
# Recursive Descent Parser
# --------------------------------

class Parser:

    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def current(self):
        return self.tokens[self.position]

    def eat(self, value=None):
        token = self.current()

        if value is not None and token["value"] != value:
            raise ParseError(
                f"Expected '{value}', found '{token['value']}'"
            )

        self.position += 1
        return token

    def parse(self):
        if self.current()["type"] == "EOF":
            raise ParseError("Please enter an expression.")

        # Assignment -> IDENTIFIER = Expression ;
        if (
            self.current()["type"] == "IDENTIFIER"
            and self.tokens[self.position + 1]["value"] == "="
        ):
            identifier = self.eat()["value"]
            self.eat("=")

            expression_parse, expression_ast = self.expression()

            children = [
                {"name": identifier},
                {"name": "="},
                expression_parse
            ]

            # Semicolon is optional.
            if self.current()["value"] == ";":
                self.eat(";")
                children.append({"name": ";"})

            if self.current()["type"] != "EOF":
                raise ParseError(
                    f"Unexpected token '{self.current()['value']}'"
                )

            parse_tree = {
                "name": "Assignment",
                "children": children
            }

            ast = {
                "name": "=",
                "children": [
                    {"name": identifier},
                    expression_ast
                ]
            }

            return parse_tree, ast

        # Otherwise, parse a normal arithmetic expression.
        parse_tree, ast = self.expression()

        # Semicolon is optional for expressions too.
        if self.current()["value"] == ";":
            self.eat(";")

        if self.current()["type"] != "EOF":
            raise ParseError(
                f"Unexpected token '{self.current()['value']}'"
            )

        return parse_tree, ast

    # Expression -> Term { (+ | -) Term }

    def expression(self):
        left_parse, left_ast = self.term()

        children = [left_parse]

        while self.current()["value"] in ("+", "-"):
            operator = self.eat()["value"]

            right_parse, right_ast = self.term()

            children.extend([
                {"name": operator},
                right_parse
            ])

            left_ast = {
                "name": operator,
                "children": [left_ast, right_ast]
            }

        return {
            "name": "Expression",
            "children": children
        }, left_ast

    # Term -> Factor { (* | /) Factor }

    def term(self):
        left_parse, left_ast = self.factor()

        children = [left_parse]

        while self.current()["value"] in ("*", "/"):
            operator = self.eat()["value"]

            right_parse, right_ast = self.factor()

            children.extend([
                {"name": operator},
                right_parse
            ])

            left_ast = {
                "name": operator,
                "children": [left_ast, right_ast]
            }

        return {
            "name": "Term",
            "children": children
        }, left_ast

    # Factor -> NUMBER | IDENTIFIER
    #         | ( Expression ) | - Factor

    def factor(self):
        token = self.current()

        # Unary minus
        if token["value"] == "-":
            self.eat("-")

            child_parse, child_ast = self.factor()

            return {
                "name": "Factor",
                "children": [
                    {"name": "-"},
                    child_parse
                ]
            }, {
                "name": "Unary -",
                "children": [child_ast]
            }

        # Parenthesized expression
        if token["value"] == "(":
            self.eat("(")

            child_parse, child_ast = self.expression()

            self.eat(")")

            return {
                "name": "Factor",
                "children": [
                    {"name": "("},
                    child_parse,
                    {"name": ")"}
                ]
            }, child_ast

        # Numbers and identifiers
        if token["type"] in ("NUMBER", "IDENTIFIER"):
            self.eat()

            leaf = {"name": token["value"]}

            return {
                "name": "Factor",
                "children": [leaf]
            }, leaf

        raise ParseError(
            f"Unexpected token '{token['value']}'. "
            "Expected a number, identifier, or '('"
        )


# --------------------------------
# Helper Functions
# --------------------------------

def count_nodes(node):
    if not isinstance(node, dict):
        return 0

    return 1 + sum(
        count_nodes(child)
        for child in node.get("children", [])
    )


def ascii_tree(node, prefix="", is_last=True, is_root=True):
    """Convert a tree into readable ASCII text."""

    if is_root:
        lines = [node["name"]]
        child_prefix = ""
    else:
        connector = "└── " if is_last else "├── "
        lines = [prefix + connector + node["name"]]

        child_prefix = prefix + (
            "    " if is_last else "│   "
        )

    children = node.get("children", [])

    for index, child in enumerate(children):
        lines.extend(
            ascii_tree(
                child,
                child_prefix,
                index == len(children) - 1,
                False
            )
        )

    return lines


# --------------------------------
# Flask Routes
# --------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse_expression():
    data = request.get_json(silent=True) or {}
    expression = data.get("expression", "")

    if not isinstance(expression, str):
        return jsonify({
            "success": False,
            "error": "Expression must be text."
        }), 400

    try:
        tokens = tokenize(expression)

        parser = Parser(tokens)

        parse_tree, ast = parser.parse()

        return jsonify({
            "success": True,
            "expression": expression,
            "tokens": [
                token for token in tokens
                if token["type"] != "EOF"
            ],
            "parse_tree": parse_tree,
            "ast": ast,
            "parse_nodes": count_nodes(parse_tree),
            "ast_nodes": count_nodes(ast),
            "ascii_parse": "\n".join(
                ascii_tree(parse_tree)
            ),
            "ascii_ast": "\n".join(
                ascii_tree(ast)
            )
        })

    except ParseError as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except RecursionError:
        return jsonify({
            "success": False,
            "error": "Expression is too deeply nested."
        }), 400


# --------------------------------
# Run Flask Application
# --------------------------------

if __name__ == "__main__":
    app.run(debug=True)
