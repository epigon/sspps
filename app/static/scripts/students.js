// Constants
const TERMS_CACHE_KEY = 'terms_with_courses_v1';
let termsWithCourses = [];
const selectedStudentIds = new Set();
const selectedStudentPIDs = new Map();
const pidToNameMap = new Map();

$(document).ready(() => {
    // ----- Term and Course Filters -----

    if (window.location.search.includes('reset_terms_cache=true')) {
        localStorage.removeItem(TERMS_CACHE_KEY);
        console.log("🗑️ Cleared terms cache.");
    }

    loadTermsWithCourses();

    const $termFilter = $('#term');
    const $courseFilter = $('#course_id');
    const selectedTermId = $termFilter.val();
    const selectedCourseId = $courseFilter.val();

    if (selectedTermId) {
        populateCourses(selectedTermId, $courseFilter, '-- All --', selectedCourseId);
    }

    $termFilter.on('change', function () {
        populateCourses(this.value, $courseFilter, '-- All --');
        $('#pdf_title, #pdf_filename').val('');
    });

    $('#course_id, #class_of').on('change', function () {
        const params = new URLSearchParams();
        const values = {
            class_of: $('#class_of').val(),
            term: $('#term').val(),
            course_id: $('#course_id').val()
        };

        for (const key in values) {
            if (values[key]) params.append(key, values[key]);
        }

        window.location.href = `${window.location.pathname}?${params.toString()}`;
    });

    const $courseSelect = $('#course_id');
    const $classSelect = $('#class_of');

    if ($courseSelect.val()) {
        const selectedOption = $courseSelect[0].selectedOptions[0];
        $('#pdf_title').val(selectedOption.text);
        $('#pdf_filename').val(selectedOption.getAttribute('data-course-code') || '');
    } else if ($classSelect.val()) {
        const selectedOption = $classSelect[0].selectedOptions[0];
        const classText = selectedOption.text;
        $('#pdf_title').val("Class of " + classText);
        $('#pdf_filename').val("class_of_" + classText);
    }

    $('#class_of').on('change', function () {
        $('#term, #course_id').val('');
        updateFilterState();

        const selectedClass = $(this).val();
        $('#students-table tbody tr').each(function () {
            const rowClass = $(this).data('class')?.toString() || '';
            $(this).toggle(!selectedClass || selectedClass === rowClass);
        });
        table.rows().invalidate().draw(false);
    });

    updateFilterState();

    // ----- DataTable + Checkbox Behavior -----

    const table = $('#students-table').DataTable({
        pageLength: 25,
        order: [],
        columnDefs: [{ orderable: false, targets: [0, 1] }]
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

    $('#photo-card-form').on('submit', function (e) {
        $('#photo-card-form input[type="hidden"][name="student_ids"]').remove();
        if (selectedStudentIds.size === 0) {
            e.preventDefault();
            return $('#client-alert').removeClass('d-none').hide().fadeIn();
        }

        selectedStudentIds.forEach(function (id) {
            const $checkbox = $('input[name="student_ids"][value="' + id + '"]');
            if (!$checkbox.length || !$checkbox.is(':checked')) {
                $('<input>').attr({ type: 'hidden', name: 'student_ids', value: id }).appendTo('#photo-card-form');
            }
        });
    });

    $('#students-table').on('click', '.delete-btn', function () {
        const studentId = $(this).data('student-id');
        if (!confirm('Are you sure you want to delete this student?')) return;

        $.post(`/students/${studentId}/delete`, { 'X-CSRFToken': "{{ form.csrf_token._value() }}" }, function (response) {
            if (response.success) {
                $(`button[data-student-id="${studentId}"]`).closest('tr').fadeOut();
                selectedStudentIds.delete(studentId.toString());
            } else {
                alert('Delete failed.');
            }
        }).fail(() => alert('An error occurred while deleting the student.'));
    });

    // ----- Enrollment Section -----

    $('#enroll-button').on('click', function () {
        const courseId = $('#enroll_course_id').val();
        const sectionId = $('#enroll_section_id').val();
        const notify = $('#notify').is(':checked');

        if (!courseId) return alert('Please select a Canvas course for enrollment.');

        const studentPIDs = Array.from(selectedStudentPIDs.values()).map(pid => `sis_user_id:${pid}`);
        if (studentPIDs.length === 0) return alert('Please select at least one student.');

        fetch("/canvas/enroll_users_bulk_api", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ course_id: courseId, users: studentPIDs, enrollment_type: "StudentEnrollment", enrollment_state: "active", notify, section_id: sectionId || null })
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

    const $enrollTermFilter = $('#enroll_term_id');
    const $enrollCourseFilter = $('#enroll_course_id');
    const selectedEnrollTermId = $enrollTermFilter.val();
    const selectedEnrollCourseId = $enrollCourseFilter.val();

    $enrollTermFilter.on('change', function () {
        populateCourses(this.value, $enrollCourseFilter, '-- All --');
    });

    if (selectedEnrollTermId) {
        $enrollTermFilter.trigger('change');
    }

    if (selectedEnrollCourseId) {
        $enrollCourseFilter.trigger('change');
    }    

    $('#enroll_course_id').on('change', function () {
        const courseId = $(this).val();
        const $sectionSelect = $('#enroll_section_id').empty().append($('<option>').val('').text('-- Entire Course --'));

        if (courseId) {
            $.get(`/canvas/get_canvas_sections_api/${courseId}`, function (sections) {
                sections.forEach(section => $sectionSelect.append($('<option>').val(section.id).text(section.name)));
            }).fail(() => alert('Failed to load sections.'));
        }
    });
});

function loadTermsWithCourses() {
    const cached = localStorage.getItem(TERMS_CACHE_KEY);
    if (cached) {
        try {
            termsWithCourses = JSON.parse(cached);
            console.log("✅ Loaded terms from localStorage.");
            return;
        } catch {
            console.warn("⚠️ Corrupt cache — falling back to embedded data.");
        }
    }
    if (window.embeddedTermsWithCourses) {
        termsWithCourses = window.embeddedTermsWithCourses;
        localStorage.setItem(TERMS_CACHE_KEY, JSON.stringify(termsWithCourses));
        console.log("✅ Cached terms from embedded data.");
    } else {
        console.error("❌ No embedded terms found.");
    }
}

function populateCourses(termId, $targetSelect, defaultOptionText = '-- Select Course --', selectedId = null) {
    $targetSelect.empty().append($('<option>').val('').text(defaultOptionText));
    $('#enroll_section_id').empty().append($('<option>').val('').text('-- Entire Course --'));

    const term = termsWithCourses.find(t => t.id.toString() === termId.toString());
    console.log(term);
    if (!term) return;

    term.courses.forEach(course => {
        const $option = $('<option>').val(course.id).attr('data-course-code', course.course_code || '').text(course.name);
        if (selectedId?.toString() === course.id.toString()) $option.prop('selected', true);
        $targetSelect.append($option);
    });
}

function updateFilterState() {
    const classOf = $('#class_of').val();
    const term = $('#term').val();
    const course = $('#course_id').val();
    $('#class_of').prop('disabled', !!(term || course));
    $('#term, #course_id').prop('disabled', !!classOf);
}