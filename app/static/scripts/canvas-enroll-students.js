// Constants
const TERMS_CACHE_KEY = 'terms_with_courses_v1';
let termsWithCourses = [];
const selectedStudentIds = new Set();
const selectedStudentPIDs = new Map();
const pidToNameMap = new Map();

document.addEventListener("DOMContentLoaded", () => {
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
    // Custom DataTables filter for "Class of" column
    // $.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {
    //     const selectedClass = $('#class_of').val();
    //     const rowClass = $($('#students-table').DataTable().row(dataIndex).node()).data('class')?.toString() || '';
    //     return !selectedClass || selectedClass === rowClass;
    // });
    $.fn.dataTable.ext.search.push(function (settings, data, dataIndex, rowData, counter) {
        const selectedClass = $('#class_of').val();
        // assumes the "Class Of" column is in column index 3 (change if needed)
        const rowClass = data[4] || '';
        return !selectedClass || selectedClass === rowClass;
    });

    // ----- DataTable + Checkbox Behavior -----
    const table = $('#students-table').DataTable({
        pageLength: 25,
        order: [],
        columnDefs: [{ orderable: false, targets: [0, 1] }],

        // v2 DOM structure
        layout: {
            topStart: 'pageLength',
            topEnd: 'search',
        },
        initComplete: function () {
            // Build Class Filter inline HTML
            const classFilterHtml = `
                    <div id="class-of-container" class="d-flex align-items-center ms-3 gap-2">
                        <label for="class_of" class="mb-0 fw-semibold">Class of:</label>
                        <select name="class_of" id="class_of" class="form-select form-select-sm" style="width:auto;">
                            <option value="">-- All --</option>
                            ${window.classYears
                    .map(y => `<option value="${y}" ${window.selectedClass === y ? 'selected' : ''}>${y}</option>`)
                    .join('')}
                        </select>
                    </div>
                `;

            // Find the v2 .dt-length container
            const lengthContainer = document.querySelector('.dt-length');
            if (lengthContainer) {
                lengthContainer.insertAdjacentHTML('beforeend', classFilterHtml);
            } else {
                console.warn('Could not find .dt-length element');
            }

            // Attach filter handler
            $('#class_of').on('change', function () {
                table.draw();
            });
        }

    });

    table.rows().every(function () {
        const $row = $(this.node());
        const checkbox = $row.find('input[name="student_ids"]');
        const studentId = checkbox.val();
        const pid = checkbox.data('pid');

        if (studentId) {
            checkbox.prop('checked', true);
            selectedStudentIds.add(studentId);
            if (pid) pidToNameMap.set(pid.toString(), ($row.find('td').eq(2).html() || '').split('<br')[0].trim());
        }
    });

    $('#check-all').prop('checked', true).on('click', function () {
        const checked = this.checked;
        table.rows({ search: 'applied' }).every(function () {
            const $checkbox = $(this.node()).find('input[name="student_ids"]');
            const id = $checkbox.val();
            const pid = $checkbox.data('pid');
            $checkbox.prop('checked', checked);
            if (checked) {
                selectedStudentIds.add(id);
                if (pid) selectedStudentPIDs.set(id, pid);
            } else {
                selectedStudentIds.delete(id);
                selectedStudentPIDs.delete(id);
            }
        });
    });

    $('#students-table').on('change', 'input[name="student_ids"]', function () {
        const id = this.value;
        const pid = $(this).data('pid');

        this.checked ? (selectedStudentIds.add(id), pid && selectedStudentPIDs.set(id, pid))
            : (selectedStudentIds.delete(id), selectedStudentPIDs.delete(id));

        const allChecked = table.rows({ page: 'current' }).nodes().to$().find('input[name="student_ids"]:not(:checked)').length === 0;
        $('#check-all').prop('checked', allChecked);
    });

    table.on('draw', function () {
        table.rows({ page: 'current' }).every(function () {
            const $checkbox = $(this.node()).find('input[name="student_ids"]');
            $checkbox.prop('checked', selectedStudentIds.has($checkbox.val()));
        });

        const allChecked = table.rows({ page: 'current' }).nodes().to$().find('input[name="student_ids"]:not(:checked)').length === 0;
        $('#check-all').prop('checked', allChecked);
    });

    // 
    // ----- Enrollment Section -----
    // 
    $('#enroll-button').on('click', function () {
        const courseId = $('#enroll_course_id').val();
        const sectionId = $('#enroll_section_id').val();
        const notify = $('#notify').is(':checked');

        if (!courseId) return alert('Please select a Canvas course for enrollment.');

        const studentPIDs = Array.from(selectedStudentPIDs.values()).map(pid => `sis_user_id:${pid}`);
        if (studentPIDs.length === 0) return alert('Please select at least one student.');

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
                users: studentPIDs,
                enrollment_type: "StudentEnrollment",
                enrollment_state: "active",
                notify: notify
            })
        })
            .then(res => res.json())
            .then(data => {
                const html = data.map(item => {
                    const pid = (item.user_id || '').replace('sis_user_id:', '');
                    const name = pidToNameMap.get(pid) || item.user_id || 'Unknown';
                    const status = item.status === 'success' ? '✅ Success' : '❌ Failed';
                    return `<li class="list-group-item d-flex justify-content-between align-items-center">${name}<span class="${item.status === 'success' ? 'text-success' : 'text-danger'}">${status}</span></li>`;
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
