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

