from app import create_app
from flask import request
from flask_bootstrap import Bootstrap5

app = create_app()
bootstrap = Bootstrap5(app)


@app.context_processor
def inject_breadcrumbs():
    path = request.path.strip('/').split('/')
    breadcrumbs = []
    cumulative_path = ''
    for segment in path:
        cumulative_path += f'/{segment}'
        breadcrumbs.append({
            'name': segment.replace('_', ' ').capitalize(),
            # 'name': segment.capitalize(),
            'url': cumulative_path
        })
    print(breadcrumbs)
    return dict(breadcrumbs=breadcrumbs)
    # in html, customize breadcrumb 
    # student = get_student(id)
    # custom_breadcrumbs = [
    #     {'name': 'Students', 'url': '/students'},
    #     {'name': f'{student.first_name} {student.last_name}', 'url': f'/students/{id}'}
    # ]

if __name__ == '__main__':
    app.run(host="0.0.0.0",debug=True,threaded=True) 