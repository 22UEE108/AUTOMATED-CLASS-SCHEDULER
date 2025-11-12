<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Class Scheduler Dashboard</title>
</head>
<body>
    <h2>Student Login</h2>
    <input type="text" id="studentId" placeholder="Student ID"><br>
    <input type="password" id="password" placeholder="Password"><br>
    <button onclick="login()">Login & Fetch Dashboard</button>

    <div id="dashboardSection" style="display:none;">
        <h3>Dashboard:</h3>
        <pre id="dashboardData"></pre>
    </div>

    <script>
        let token = '';

        async function login() {
            const studentId = document.getElementById('studentId').value;
            const password = document.getElementById('password').value;

            if (!studentId || !password) {
                alert("Enter Student ID and Password");
                return;
            }

            try {
                // Call backend login endpoint
                const res = await fetch('http://localhost:8000/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ student_id: studentId, password: password })
                });
                if (!res.ok) throw new Error("Login failed");
                const data = await res.json();
                token = data.token;

                // Fetch dashboard
                const dashRes = await fetch(`http://localhost:8000/dashboard/${studentId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const dashData = await dashRes.json();

                document.getElementById('dashboardSection').style.display = 'block';
                document.getElementById('dashboardData').textContent = JSON.stringify(dashData, null, 2);

            } catch (err) {
                alert("Error: " + err.message);
            }
        }
    </script>
</body>
</html>
