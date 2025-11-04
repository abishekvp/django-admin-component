// toastr.options = {
//     "progressBar": true,
//     "positionClass": "toast-top-center"
// }

$("#restart-bot").click(function() {
    alert("Restarting bot...");
    $.ajax({
        url: '/start-bot',
        type: 'GET',
        success: function(response) {
            alert("Bot restarted successfully!");
            // toastr.success('Bot restarted successfully!');
        },
        error: function(xhr, status, error) {
            alert("Error restarting bot: " + error);
            // toastr.error('Error restarting bot: ' + error);
        }
    });
});

function add_source_group() {
    var group_username = prompt("Enter the group username (without @):");
    var group_title = prompt("Enter the group title:");

    if (group_username && group_title) {
        $.ajax({
            url: '/add-source-group',
            type: 'POST',
            data: {
                'group_username': group_username,
                'group_title': group_title,
                'csrfmiddlewaretoken': $('input[name="csrfmiddlewaretoken"]').val()
            },
            success: function(response) {
                alert("Source group added successfully!");
                location.reload(); // Reload the page to show the new group
            },
            error: function(xhr, status, error) {
                alert("Error adding source group: " + error);
            }
        });
    } else {
        alert("Group username and title are required.");
    }
}