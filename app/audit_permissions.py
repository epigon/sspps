import ast
import os

class RoutePermissionChecker(ast.NodeVisitor):
    def __init__(self):
        self.routes_without_permission = []

    def visit_FunctionDef(self, node):
        is_route = False
        has_permission_required = False

        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "route":
                        is_route = True
                if isinstance(decorator.func, ast.Name):
                    if decorator.func.id == "permission_required":
                        has_permission_required = True
            elif isinstance(decorator, ast.Name):
                if decorator.id == "permission_required":
                    has_permission_required = True

        if is_route and not has_permission_required:
            self.routes_without_permission.append(node.name)

        self.generic_visit(node)

def check_file(filepath):
    with open(filepath, "r") as file:
        tree = ast.parse(file.read(), filename=filepath)
    
    checker = RoutePermissionChecker()
    checker.visit(tree)

    return checker.routes_without_permission

if __name__ == "__main__":

    for path in ['routes.py', 'committee_tracker/routes.py']:
        # path = "routes.py"  # Replace with your path
        # path = "admin/routes.py"  # Replace with your path
        # path = "committee_tracker/routes.py"  # Replace with your path
        if os.path.exists(path):
            missing = check_file(path)
            if missing:
                print("❌ Route functions missing @permission_required:")
                for fn in missing:
                    print(f" - {fn}")
            else:
                print("✅ All route functions have @permission_required.")
        else:
            print(f"File not found: {path}")
