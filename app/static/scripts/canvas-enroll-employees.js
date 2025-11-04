// employees.js
$(document).ready(() => {
    // 
    // ----- Filter section -----
    // 
    const $termFilter = $('#enroll_term_id');
    const $courseFilter = $('#enroll_course_id');
    const $sectionSelect = $('#enroll_section_id');

    const termsWithCourses = window.embeddedTermsWithCourses || [];

    $termFilter.on('change', function () {
        populateCourses(this.value, $courseFilter, '-- Select Course --');
    });

    $courseFilter.on('change', function () {
        $sectionSelect.empty().append($('<option>').val('').text('-- Entire Course --'));
        const courseId = $courseFilter.val();
        if (courseId) {
            $.get(`/canvas/get_canvas_sections_api/${courseId}`, function (sections) {
                sections.forEach(section =>
                    $sectionSelect.append($('<option>').val(section.id).text(section.name))
                );
            }).fail(() => alert('Failed to load sections.'));
        }
        // --- Clear results progress ---
        $('#resultArea').html('');
    });

    // 
    // ----- Datatable section -----
    // 
    const selectedEmployeePIDs = new Set();
    // index of the column that contains the checkbox
    const checkboxColIndex = 0;
    const $table = $('#employees-table');

    const table = $table.DataTable({
        pageLength: 25,
        order: [],
        columnDefs: [
            { orderable: false, targets: [checkboxColIndex] }
        ]
    });

    // --- Handle checking/unchecking ---
    $table.on('change', 'input[name="employee_ids"]', function () {
        const pid = $(this).data('pid');
        if (this.checked) selectedEmployeePIDs.add(pid);
        else selectedEmployeePIDs.delete(pid);
        refreshPinnedRows();
    });

    $('#check-all').on('click', function () {
        const checked = this.checked;
        table.rows({ search: 'applied' }).every(function () {
            const $checkbox = $(this.node()).find('input[name="employee_ids"]');
            const pid = $checkbox.data('pid');
            $checkbox.prop('checked', checked);
            if (checked) selectedEmployeePIDs.add(pid);
            else selectedEmployeePIDs.delete(pid);
        });
        refreshPinnedRows();
    });

    // --- Keep checked & highlight ---
    function highlightPinned() {
        table.rows().every(function () {
            const $row = $(this.node());
            const $checkbox = $row.find('input[name="employee_ids"]');
            const pid = $checkbox.data('pid');
            const pinned = selectedEmployeePIDs.has(pid);
            $checkbox.prop('checked', pinned);
            $row.toggleClass('table-warning', pinned);
        });
    }

    // --- Custom: ensure pinned rows always visible even if search hides them ---
    function refreshPinnedRows() {
        // Store current search
        const searchValue = table.search();

        // Clear search temporarily to get all rows
        table.search('').draw();

        // For each pinned PID, show its row if hidden
        table.rows().every(function () {
            const $row = $(this.node());
            const pid = $row.find('input[name="employee_ids"]').data('pid');
            const isPinned = selectedEmployeePIDs.has(pid);
            if (isPinned) {
                $row.show(); // force visible
                $row.prependTo($table.find('tbody')); // move to top
            }
        });

        // Reapply search for non-pinned rows
        if (searchValue) {
            table.search(searchValue).draw();
            // After draw, bring pinned rows back to top again
            setTimeout(() => {
                table.rows().every(function () {
                    const $row = $(this.node());
                    const pid = $row.find('input[name="employee_ids"]').data('pid');
                    if (selectedEmployeePIDs.has(pid)) {
                        $row.show();
                        $row.prependTo($table.find('tbody'));
                    }
                });
                highlightPinned();
            }, 0);
        } else {
            highlightPinned();
        }
    }

    // --- Reapply highlighting after any redraw ---
    table.on('draw', function () {
        highlightPinned();

        // Move pinned rows to top of table
        selectedEmployeePIDs.forEach(pid => {
            const $row = $table.find(`input[data-pid="${pid}"]`).closest('tr');
            $row.prependTo($table.find('tbody'));
        });
    });

    // --- Refresh whenever search input changes ---
    $table.closest('.dataTables_wrapper').find('input[type=search]').on('input', function () {
        refreshPinnedRows();
    });
    // 
    // ----- Enrollment Section -----
    // 
    $('#enroll-button').on('click', () => {
        console.log('Enroll button clicked');
        const courseId = $courseFilter.val();
        const sectionId = $sectionSelect.val();
        const notify = $('#notify').is(':checked');
        const role = $('#role_type').val();
        const users = Array.from(selectedEmployeePIDs).map(pid => `sis_user_id:${pid}`);
        // console.log('Selected course ID:', courseId);
        // console.log('Selected section ID:', sectionId);
        // console.log('Notify:', notify);
        // console.log('Role:', role);
        // console.log('Users to enroll:', users);
        // return;

        if (!courseId) return alert('Please select a course.');
        if (users.length === 0) return alert('Please select at least one employee.');

        // --- Show progress ---
        $('#resultArea').html(`
            <div class="d-flex align-items-center">
                <strong>Enrolling users...</strong>
                <div class="spinner-border spinner-border-sm ms-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>
        `);
        
        fetch("/canvas/enroll_users_bulk_api", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                course_id: courseId,
                section_id: sectionId || null,
                users: users,
                enrollment_type: role,
                enrollment_state: "active",
                notify: notify
            })
        })
            .then(res => res.json())
            .then(data => {
                const html = data.map(item => {
                    const pid = (item.user_id || '').replace('sis_user_id:', '');
                    const status = item.status === 'success' ? '✅ Success' : '❌ Failed';
                    return `<li class="list-group-item d-flex justify-content-between align-items-center">${pid}<span class="${item.status === 'success' ? 'text-success' : 'text-danger'}">${status}</span></li>`;
                }).join('');
                $('#resultArea').html(`<h5>Enrollment Results:</h5><ul class='list-group'>${html}</ul>`);
            })
            .catch(err => $('#resultArea').html(`<div class='text-danger'>Error: ${err}</div>`));
    });

    function populateCourses(termId, $targetSelect, defaultOptionText = '-- Select Course --') {
        $targetSelect.empty().append($('<option>').val('').text(defaultOptionText));
        const term = termsWithCourses.find(t => t.id.toString() === termId.toString());
        if (!term) return;

        term.courses.forEach(course => {
            const $option = $('<option>').val(course.id).attr('data-course-code', course.course_code || '').text(course.name);
            $targetSelect.append($option);
        });
    }
});
