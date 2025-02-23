import numpy as np
from scipy.optimize import least_squares



def read_matches_file(filename, image_id1, image_id2):
    """
    Parse matches.txt file to extract corresponding points between two specific images.
    Returns points and their corresponding line numbers.
    """
    points1 = []
    points2 = []
    line_numbers = []  # List to store line numbers where matches are found
    no_match_count = 0  # Initialize the variable
    
    with open(filename, 'r') as f:
        # Read and process all lines
        lines = f.readlines()
        
        # Find the first non-empty line
        n_features = 0
        for line in lines:
            line = line.strip()
            if line:  # if line is not empty
                if 'nFeatures' in line:
                    n_features = int(line.split(': ')[1])
                    break
        
        # Process each feature line
        current_feature = 0
        line_idx = 1  # Start from next line after nFeatures
        
        while current_feature < n_features and line_idx < len(lines):
            # Get next non-empty line
            while line_idx < len(lines):
                line = lines[line_idx].strip()
                if line:  # if line is not empty
                    break
                line_idx += 1
            
            if line_idx >= len(lines):
                break
                
            try:
                # Split the line and convert to numbers
                values = line.split()
                if not values:  # Skip if line is empty after splitting
                    line_idx += 1
                    continue
                    
                line_data = [float(x) for x in values]
                
                n_matches = int(line_data[0])
                current_u, current_v = line_data[4:6]
                matches_data = line_data[6:]  # Skip count, RGB, and current coords
                
                found_match = False  # Track if any match is found
                
                # Look through matches to find if either target image is present
                for i in range(0, len(matches_data), 3):
                    if i + 2 >= len(matches_data):
                        break
                        
                    match_image_id = int(matches_data[i])
                    match_u = matches_data[i + 1]
                    match_v = matches_data[i + 2]
                    
                    if match_image_id == image_id2:
                        points1.append([current_u, current_v])
                        points2.append([match_u, match_v])
                        line_numbers.append(line_idx + 1)  # +1 to convert zero-index to actual line number
                        found_match = True
                    elif match_image_id == image_id1:
                        points2.append([current_u, current_v])
                        points1.append([match_u, match_v])
                        line_numbers.append(line_idx + 1)  # +1 to convert zero-index to actual line number
                        found_match = True
                
                # If no match found, increase the counter
                if not found_match:
                    no_match_count += 1
            
            except (ValueError, IndexError) as e:
                print(f"Warning: Error processing line {line_idx + 1}: {e}")
                
            current_feature += 1
            line_idx += 1

    print(f"Total Features: {n_features}, Features with No Matches: {no_match_count}")
    return np.array(points1), np.array(points2), line_numbers


def EstimateFundamentalMatrix(points1, points2):

    # Convert points to homogeneous coordinates
    points1_h = np.hstack((points1, np.ones((points1.shape[0], 1))))
    points2_h = np.hstack((points2, np.ones((points2.shape[0], 1))))
    
    # Build the constraint matrix
    A = np.zeros((points1.shape[0], 9))
    for i in range(points1.shape[0]):
        x1, y1 = points1_h[i, :2]
        x2, y2 = points2_h[i, :2]
        A[i] = [x2*x1, x2*y1, x2, y2*x1, y2*y1, y2, x1, y1, 1]
    
    # Solve for F using SVD
    _, _, V = np.linalg.svd(A)
    F = V[-1].reshape(3, 3)
    
    # Enforce rank 2 constraint
    U, S, V = np.linalg.svd(F)
    S[2] = 0
    F = U @ np.diag(S) @ V
    
    return F

# Just to check if the fundamental matrix is correct
def calculate_epipolar_error(F, points1, points2):
    """
    Calculate epipolar constraint error for the fundamental matrix.
    """
    points1_h = np.hstack((points1, np.ones((points1.shape[0], 1))))
    points2_h = np.hstack((points2, np.ones((points2.shape[0], 1))))
    
    # Calculate epipolar constraint x2.T * F * x1
    errors = []
    for i in range(len(points1)):
        error = abs(points2_h[i].dot(F.dot(points1_h[i])))
        errors.append(error)
    
    return np.mean(errors)


def GetInlierRANSANC(points1, points2, line_numbers, num_iterations=1000, threshold=0.125):

    best_F = None
    best_inliers = []
    best_inlier_count = 0
    best_inlier_lines = []
    
    if len(points1) < 8:
        print("Not enough points for RANSAC (need at least 8)")
        return None, [], []
    
    num_points = len(points1)
    
    for i in range(num_iterations):
        # 1. Randomly select 8 correspondences
        sample_indices = np.random.choice(num_points, 8, replace=False)
        sample_points1 = points1[sample_indices]
        sample_points2 = points2[sample_indices]
        
        # 2. Compute fundamental matrix from these samples
        F = EstimateFundamentalMatrix(sample_points1, sample_points2)
        
        # 3. Determine inliers based on epipolar constraint
        inliers = []
        inlier_lines = []
        
        # Convert points to homogeneous coordinates
        points1_h = np.hstack((points1, np.ones((num_points, 1))))
        points2_h = np.hstack((points2, np.ones((num_points, 1))))
        
        # Check each correspondence
        for j in range(num_points):
            # Calculate epipolar constraint error: |x2^T F x1|
            error = abs(points2_h[j].dot(F.dot(points1_h[j])))
            
            # If error is small enough, consider it an inlier
            if error < threshold:
                inliers.append(j)
                inlier_lines.append(line_numbers[j])
        
        # 4. Update best model if we found more inliers
        if len(inliers) > best_inlier_count:
            best_inlier_count = len(inliers)
            best_inliers = inliers
            best_F = F
            best_inlier_lines = inlier_lines
    
    print(f"RANSAC found {best_inlier_count} inliers out of {num_points} points")
    
    # Optionally, recompute F using all inliers for better accuracy
    if len(best_inliers) >= 8:
        inlier_points1 = points1[best_inliers]
        inlier_points2 = points2[best_inliers]
        best_F = EstimateFundamentalMatrix(inlier_points1, inlier_points2)
    
    return best_F, best_inliers, best_inlier_lines

def EssentialMatrixFromFundamentalMatrix(F, K):

    E = K.T @ F @ K
    U, _, Vt = np.linalg.svd(E)
    E = U @ np.diag([1, 1, 0]) @ Vt
    return E

def ExtractCameraPose(E):
    """
    Extract camera pose (R,C) from Essential matrix.
    Returns four possible camera pose configurations.
    
    Args:
        E: Essential matrix (3x3)
    
    Returns:
        Rs: List of four possible rotation matrices [R1, R2, R3, R4]
        Cs: List of four possible camera centers [C1, C2, C3, C4]
    """
    U, _, Vt = np.linalg.svd(E)
    
    # Define W matrix
    W = np.array([
        [0, -1, 0],
        [1, 0, 0],
        [0, 0, 1]
    ])
    
    # Four possible configurations
    R1 = U @ W @ Vt
    R2 = U @ W @ Vt
    R3 = U @ W.T @ Vt
    R4 = U @ W.T @ Vt
    
    # Extract camera centers
    C1 = U[:, 2]
    C2 = -U[:, 2]
    C3 = U[:, 2]
    C4 = -U[:, 2]
    
    # Ensure rotation matrices are valid (det(R) = 1)
    Rs = [R1, R2, R3, R4]
    Cs = [C1, C2, C3, C4]
    
    # Correct rotation matrices if det(R) = -1
    for i in range(4):
        if np.linalg.det(Rs[i]) < 0:
            Rs[i] = -Rs[i]
            Cs[i] = -Cs[i]
    
    return Rs, Cs

def LinearTriangulation(K, C1, R1, C2, R2, points1, points2):
    """
    Triangulate 3D points from two camera poses and point correspondences.
    Also performs cheirality check to determine correct camera pose.
    
    Args:
        K: Camera calibration matrix (3x3)
        C1, C2: Camera centers
        R1, R2: Rotation matrices
        points1, points2: Corresponding points in two images
        
    Returns:
        X: 3D points in world coordinates
        valid_indices: Indices of points that pass cheirality check
    """
    # Number of points
    num_points = points1.shape[0]
    X = np.zeros((num_points, 3))
    valid_indices = []
    
    # Convert camera centers to column vectors
    C1 = C1.reshape(3, 1)
    C2 = C2.reshape(3, 1)
    
    # Compute projection matrices
    P1 = K @ R1 @ np.hstack([np.eye(3), -C1])
    P2 = K @ R2 @ np.hstack([np.eye(3), -C2])
    
    for i in range(num_points):
        # Get corresponding points
        x1 = points1[i]
        x2 = points2[i]
        
        # Convert to homogeneous coordinates
        x1_h = np.append(x1, 1)
        x2_h = np.append(x2, 1)
       
        # Create the A matrix for linear triangulation
        A = np.zeros((4, 4))
        
        # For point x1
        A[0] = x1_h[0] * P1[2] - P1[0]
        A[1] = x1_h[1] * P1[2] - P1[1]
        
        # For point x2
        A[2] = x2_h[0] * P2[2] - P2[0]
        A[3] = x2_h[1] * P2[2] - P2[1]
        
        # Solve for X using SVD
        _, _, Vt = np.linalg.svd(A)
        X_h = Vt[-1]
        
        # Convert from homogeneous to 3D coordinates
        X_h = X_h / X_h[-1]
        X[i] = X_h[:3]
        
        # Perform cheirality check for this point
        # Check if point is in front of both cameras
        X_3D = X[i].reshape(3, 1)
        
        # Check if the 3D point is in front of the first camera
        condition1 = R1[2] @ (X_3D - C1) > 0
        
        # Check if the 3D point is in front of the second camera
        condition2 = R2[2] @ (X_3D - C2) > 0
        
        if condition1 and condition2:
            valid_indices.append(i)
    
    return X, valid_indices


def DisambiguateCameraPose(Rs, Cs, K, points1, points2):
    """
    Disambiguate camera pose by checking which configuration has the most points
    passing the cheirality check.
    
    Args:
        Rs: List of four possible rotation matrices
        Cs: List of four possible camera centers
        K: Camera calibration matrix
        points1, points2: Corresponding points in two images
        
    Returns:
        R_best, C_best: The best camera pose
        X_best: The triangulated 3D points
        valid_indices: Indices of valid points
    """
    max_valid_points = 0
    best_config = 0
    X_best = None
    valid_indices_best = None
    
    # First camera pose (canonical camera [I|0])
    R1 = np.eye(3)
    C1 = np.zeros((3, 1))
    
    # Test all four configurations
    for i in range(4):
        X, valid_indices = LinearTriangulation(K, C1, R1, Cs[i], Rs[i], points1, points2)
        
        # Count valid points
        num_valid = len(valid_indices)
        
        if num_valid > max_valid_points:
            max_valid_points = num_valid
            best_config = i
            X_best = X
            valid_indices_best = valid_indices
    
    print(f"Selected camera pose configuration {best_config+1} with {max_valid_points} valid points")
    
    return Rs[best_config], Cs[best_config], X_best, valid_indices_best

def compute_reprojection_error(X, P1, P2, point1, point2):
    """
    Compute reprojection error for a single 3D point
    
    Args:
        X: 3D point (3,)
        P1, P2: Camera projection matrices (3,4)
        point1, point2: Measured 2D points in both images
    
    Returns:
        Array of reprojection errors [e1x, e1y, e2x, e2y]
    """
    # Convert X to homogeneous coordinates
    X_homog = np.append(X, 1)
    
    # Project 3D point into both images
    proj1 = P1 @ X_homog
    proj2 = P2 @ X_homog
    
    # Convert to inhomogeneous coordinates
    proj1 = proj1[:2] / proj1[2]
    proj2 = proj2[:2] / proj2[2]
    
    # Compute reprojection errors
    errors = np.concatenate([
        point1 - proj1,
        point2 - proj2
    ])
    
    return errors

def NonLinearTriangulation(K, R1, C1, R2, C2, points1, points2, X_initial):
    """
    Refine 3D points using non-linear optimization to minimize reprojection error
    
    Args:
        K: Camera calibration matrix (3,3)
        R1, C1: First camera pose
        R2, C2: Second camera pose
        points1, points2: 2D point correspondences
        X_initial: Initial 3D points from linear triangulation
    
    Returns:
        X_refined: Refined 3D points
    """
    # Compute projection matrices
    C1 = C1.reshape(3, 1)
    C2 = C2.reshape(3, 1)
    P1 = K @ R1 @ np.hstack([np.eye(3), -C1])
    P2 = K @ R2 @ np.hstack([np.eye(3), -C2])
    
    X_refined = np.zeros_like(X_initial)
    
    # Refine each point independently
    for i in range(len(X_initial)):
        def objective(X):
            return compute_reprojection_error(X, P1, P2, points1[i], points2[i])
        
        # Use least_squares to minimize reprojection error
        result = least_squares(
            objective,
            X_initial[i],
            method='lm',  # Levenberg-Marquardt algorithm
            max_nfev=50   # Maximum number of function evaluations
        )
        
        X_refined[i] = result.x
        
    return X_refined


def VisualizeReconstruction(X, R2, C2):
    """
    Visualize the 3D reconstruction.
    
    Args:
        X: 3D points
        R2, C2: Second camera pose
    """
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot the 3D points
        ax.scatter(X[:, 0], X[:, 1], X[:, 2], c='b', marker='.', s=1)
        
        # Plot the cameras
        # Camera 1 at origin
        ax.scatter(0, 0, 0, c='r', marker='o', s=100, label='Camera 1')
        
        # Camera 2
        C2_pos = C2.flatten()
        ax.scatter(C2_pos[0], C2_pos[1], C2_pos[2], c='g', marker='o', s=100, label='Camera 2')
        
        # Draw camera orientation
        # Camera 1 orientation
        for i in range(3):
            ax.quiver(0, 0, 0, 
                      0.5 if i==0 else 0, 
                      0.5 if i==1 else 0, 
                      0.5 if i==2 else 0, 
                      color=['r', 'g', 'b'][i])
        
        # Camera 2 orientation
        for i in range(3):
            ax.quiver(C2_pos[0], C2_pos[1], C2_pos[2],
                     R2[0, i]*0.5, R2[1, i]*0.5, R2[2, i]*0.5,
                     color=['r', 'g', 'b'][i])
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.legend()
        
        plt.title('3D Reconstruction with Camera Poses')
        plt.show()
    except ImportError:
        print("Matplotlib not available for visualization")

def VisualizeReconstructionComparison(X_initial, X_refined, R2, C2):
    """
    Visualize both initial and refined 3D reconstructions in the same plot.
    
    Args:
        X_initial: Initial 3D points from linear triangulation
        X_refined: Refined 3D points after non-linear optimization
        R2, C2: Second camera pose
    """
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot the initial 3D points in red
        ax.scatter(X_initial[:, 0], X_initial[:, 1], X_initial[:, 2], 
                  c='red', marker='.', s=10, label='Initial Points (Linear)')
        
        # Plot the refined 3D points in blue
        ax.scatter(X_refined[:, 0], X_refined[:, 1], X_refined[:, 2], 
                  c='blue', marker='.', s=10, label='Refined Points (Non-linear)')
        
        # Plot the cameras
        # Camera 1 at origin
        ax.scatter(0, 0, 0, c='green', marker='o', s=100, label='Camera 1')
        
        # Camera 2
        C2_pos = C2.flatten()
        ax.scatter(C2_pos[0], C2_pos[1], C2_pos[2], c='yellow', marker='o', s=100, label='Camera 2')
        
        # Draw camera orientation vectors
        # Camera 1 orientation
        colors = ['r', 'g', 'b']
        for i in range(3):
            ax.quiver(0, 0, 0, 
                     0.5 if i==0 else 0, 
                     0.5 if i==1 else 0, 
                     0.5 if i==2 else 0, 
                     color=colors[i], alpha=0.5)
        
        # Camera 2 orientation
        for i in range(3):
            ax.quiver(C2_pos[0], C2_pos[1], C2_pos[2],
                     R2[0, i]*0.5, R2[1, i]*0.5, R2[2, i]*0.5,
                     color=colors[i], alpha=0.5)
        
        # Add displacement arrows between initial and refined points
        for i in range(len(X_initial)):
            ax.plot([X_initial[i, 0], X_refined[i, 0]],
                   [X_initial[i, 1], X_refined[i, 1]],
                   [X_initial[i, 2], X_refined[i, 2]],
                   'k-', alpha=0.2, linewidth=0.5)
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.legend()
        
        # Add title with axis scales
        plt.title('3D Reconstruction Comparison: Initial vs Refined Points')
        
        # Auto-adjust the view
        ax.set_box_aspect([1, 1, 1])
        
        plt.show()
        
        # Create a second plot showing the displacement magnitudes
        displacements = np.sqrt(np.sum((X_refined - X_initial)**2, axis=1))
        
        plt.figure(figsize=(10, 5))
        plt.hist(displacements, bins=50, color='blue', alpha=0.7)
        plt.xlabel('Displacement Magnitude')
        plt.ylabel('Number of Points')
        plt.title('Histogram of Point Displacements after Non-linear Optimization')
        plt.show()
        
    except ImportError:
        print("Matplotlib not available for visualization")

def VisualizeXZPlaneViewInitial(X_initial, R2, C2):
    """
    Visualize just the XZ plane view of initial 3D reconstruction.
    
    Args:
        X_initial: Initial 3D points from linear triangulation
        R2, C2: Second camera pose
    """
    try:
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(12, 8))
        
        # Plot the initial points
        plt.scatter(X_initial[:, 0], X_initial[:, 2], 
                   c='red', marker='.', s=30, label='Initial Points',
                   alpha=0.6)
        
        # Plot the cameras
        # Camera 1 at origin
        plt.scatter(0, 0, c='green', marker='o', s=100, label='Camera 1')
        
        # Camera 2
        C2_pos = C2.flatten()
        plt.scatter(C2_pos[0], C2_pos[2], c='yellow', marker='o', s=100, label='Camera 2')
        
        # Draw camera orientation vectors
        # Camera 1
        plt.arrow(0, 0, 0.5, 0, head_width=0.1, head_length=0.1, fc='g', ec='g', alpha=0.5)
        plt.arrow(0, 0, 0, 0.5, head_width=0.1, head_length=0.1, fc='g', ec='g', alpha=0.5)
        
        # Camera 2
        plt.arrow(C2_pos[0], C2_pos[2], 
                 R2[0, 0]*0.5, R2[2, 0]*0.5, 
                 head_width=0.1, head_length=0.1, fc='y', ec='y', alpha=0.5)
        plt.arrow(C2_pos[0], C2_pos[2], 
                 R2[0, 2]*0.5, R2[2, 2]*0.5, 
                 head_width=0.1, head_length=0.1, fc='y', ec='y', alpha=0.5)
        
        plt.xlabel('X')
        plt.ylabel('Z')
        plt.title('XZ Plane View - Initial 3D Points')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Make axes equal to preserve scale
        plt.axis('equal')
        
        plt.show()
        
    except ImportError:
        print("Matplotlib not available for visualization")

def VisualizeXZPlaneView(X_initial, X_refined, R2, C2):
    """
    Visualize the XZ plane view of both initial and refined 3D reconstructions.
    
    Args:
        X_initial: Initial 3D points from linear triangulation
        X_refined: Refined 3D points after non-linear optimization
        R2, C2: Second camera pose
    """
    try:
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(12, 8))
        
        # Plot the initial points in red
        plt.scatter(X_initial[:, 0], X_initial[:, 2], 
                   c='red', marker='.', s=30, label='Initial Points (Linear)',
                   alpha=0.6)
        
        # Plot the refined points in blue
        plt.scatter(X_refined[:, 0], X_refined[:, 2], 
                   c='blue', marker='.', s=30, label='Refined Points (Non-linear)',
                   alpha=0.6)
        
        # Plot the cameras
        # Camera 1 at origin
        plt.scatter(0, 0, c='green', marker='o', s=100, label='Camera 1')
        
        # Camera 2
        C2_pos = C2.flatten()
        plt.scatter(C2_pos[0], C2_pos[2], c='yellow', marker='o', s=100, label='Camera 2')
        
        # Draw displacement lines
        for i in range(len(X_initial)):
            plt.plot([X_initial[i, 0], X_refined[i, 0]],
                    [X_initial[i, 2], X_refined[i, 2]],
                    'k-', alpha=0.2, linewidth=0.5)
        
        # Draw camera orientation vectors
        # Camera 1
        plt.arrow(0, 0, 0.5, 0, head_width=0.1, head_length=0.1, fc='g', ec='g', alpha=0.5)
        plt.arrow(0, 0, 0, 0.5, head_width=0.1, head_length=0.1, fc='g', ec='g', alpha=0.5)
        
        # Camera 2
        plt.arrow(C2_pos[0], C2_pos[2], 
                 R2[0, 0]*0.5, R2[2, 0]*0.5, 
                 head_width=0.1, head_length=0.1, fc='y', ec='y', alpha=0.5)
        plt.arrow(C2_pos[0], C2_pos[2], 
                 R2[0, 2]*0.5, R2[2, 2]*0.5, 
                 head_width=0.1, head_length=0.1, fc='y', ec='y', alpha=0.5)
        
        plt.xlabel('X')
        plt.ylabel('Z')
        plt.title('XZ Plane View of 3D Reconstruction')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Make axes equal to preserve scale
        plt.axis('equal')
        
        plt.show()
        
    except ImportError:
        print("Matplotlib not available for visualization")

def calculate_mean_reprojection_error(X, K, R1, C1, R2, C2, points1, points2):
    """
    Calculate mean reprojection error across all points
    """
    C1 = C1.reshape(3, 1)
    C2 = C2.reshape(3, 1)
    P1 = K @ R1 @ np.hstack([np.eye(3), -C1])
    P2 = K @ R2 @ np.hstack([np.eye(3), -C2])
    
    total_error = 0
    
    for i in range(len(X)):
        errors = compute_reprojection_error(X[i], P1, P2, points1[i], points2[i])
        total_error += np.sqrt(np.sum(errors**2)) / 2  # Average error across both images
        
    return total_error / len(X)


def VisualizeImagePoints(points1, points2, K, R1, C1, R2, C2, X_initial, X_refined, img1_path, img2_path):
    """
    Visualize original and reprojected points overlaid on both images in a grid layout.
    Top row: Linear triangulation results
    Bottom row: Non-linear triangulation results
    
    Args:
        points1, points2: Original feature points in both images
        K: Camera calibration matrix
        R1, C1: First camera pose (typically identity and zero)
        R2, C2: Second camera pose
        X_initial: 3D points from linear triangulation
        X_refined: 3D points from non-linear optimization
        img1_path, img2_path: Paths to the input images
    """
    try:
        import matplotlib.pyplot as plt
        import cv2
        
        # Read images
        img1 = cv2.imread(img1_path)
        img2 = cv2.imread(img2_path)
        
        # Convert BGR to RGB
        img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
        img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)
        
        # Create a 2x2 grid of plots
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # Function to plot points for one image
        def plot_points(ax, img, orig_points, proj_points, title):
            # Show the image
            ax.imshow(img)
            
            ax.scatter(orig_points[:, 0], orig_points[:, 1], 
                      c='lime', marker='o', s=20, label='Original Points',
                      alpha=0.7)
            
            # Plot reprojected points in green
            ax.scatter(proj_points[:, 0], proj_points[:, 1], 
                      c='red', marker='o', s=20, label='Reprojected Points',
                      alpha=0.7)
            
            
            ax.set_title(title)
            ax.legend()
            
            # Remove axis ticks but keep the image extent
            ax.set_xticks([])
            ax.set_yticks([])
        
        # Get reprojected points
        def project_3D_points(X, K, R, C):
            C = C.reshape(3, 1)
            P = K @ R @ np.hstack([np.eye(3), -C])
            
            # Convert X to homogeneous coordinates and project
            X_homog = np.hstack((X, np.ones((X.shape[0], 1))))
            proj_points = []
            
            for X_i in X_homog:
                # Project point
                x = P @ X_i
                # Convert to inhomogeneous coordinates
                x = x[:2] / x[2]
                proj_points.append(x)
            
            return np.array(proj_points)
        
        # Get reprojections for linear triangulation
        proj1_linear = project_3D_points(X_initial, K, R1, C1)
        proj2_linear = project_3D_points(X_initial, K, R2, C2)
        
        # Get reprojections for non-linear triangulation
        proj1_nonlinear = project_3D_points(X_refined, K, R1, C1)
        proj2_nonlinear = project_3D_points(X_refined, K, R2, C2)
        
        # Plot linear triangulation results
        plot_points(axes[0, 0], img1, points1, proj1_linear, 'Image 1 - Linear Triangulation')
        plot_points(axes[0, 1], img2, points2, proj2_linear, 'Image 2 - Linear Triangulation')
        
        # Plot non-linear triangulation results
        plot_points(axes[1, 0], img1, points1, proj1_nonlinear, 'Image 1 - Non-linear Triangulation')
        plot_points(axes[1, 1], img2, points2, proj2_nonlinear, 'Image 2 - Non-linear Triangulation')
        
        # Adjust layout
        plt.tight_layout()
        plt.show()
        
        # Calculate and print mean reprojection errors
        def calculate_mean_error(points, proj_points):
            return np.mean(np.sqrt(np.sum((points - proj_points)**2, axis=1)))
        
        # print("\nMean Reprojection Errors:")
        # print(f"Linear Triangulation:")
        # print(f"  Image 1: {calculate_mean_error(points1, proj1_linear):.4f} pixels")
        # print(f"  Image 2: {calculate_mean_error(points2, proj2_linear):.4f} pixels")
        # print(f"Non-linear Triangulation:")
        # print(f"  Image 1: {calculate_mean_error(points1, proj1_nonlinear):.4f} pixels")
        # print(f"  Image 2: {calculate_mean_error(points2, proj2_nonlinear):.4f} pixels")
        
    except ImportError:
        print("Matplotlib or OpenCV not available for visualization")

def main():
    # Example usage with your matches.txt file
    matches_file = 'matching1.txt'
    image_id1 = 1  # Replace with your first image ID
    image_id2 = 2 # Replace with your second image ID
    image1_path = r'C:\Users\farha\OneDrive\Desktop\P2Data\P2Data\1.png'
    image2_path = r'C:\Users\farha\OneDrive\Desktop\P2Data\P2Data\2.png'
    
    # Parse matching points
    points1, points2, line_numbers = read_matches_file(matches_file, image_id1, image_id2)
    
    print(f"Found {len(points1)} potential matches")
    
    if len(points1) < 8:
        print(f"Not enough matches found between images {image_id1} and {image_id2}")
        print(f"Found {len(points1)} matches, need at least 8")
        return
    
    # Run RANSAC to find inliers and estimate F
    best_F, inliers, inlier_lines = GetInlierRANSANC(points1, points2, line_numbers)
    
    # Calculate error using inliers
    if len(inliers) >= 8:
        inlier_points1 = points1[inliers]
        inlier_points2 = points2[inliers]
        error = calculate_epipolar_error(best_F, inlier_points1, inlier_points2)
        
        print("\nFundamental Matrix:")
        print(best_F)
        print(f"\nNumber of inliers: {len(inliers)} out of {len(points1)} points")
        # print("Line numbers of inliers:", inlier_lines)
        print("\nAverage Epipolar Error for inliers:", error)
    else:
        print("Failed to find enough inliers using RANSAC")

    K = np.loadtxt('calibration.txt')
    E = EssentialMatrixFromFundamentalMatrix(best_F,K)
    

    Rs,Cs = ExtractCameraPose(E)

    # Disambiguate camera pose using cheirality check
    R_best, C_best, X_best, valid_indices = DisambiguateCameraPose(Rs, Cs, K, inlier_points1, inlier_points2)
    
    # Extract valid points
    valid_points1 = inlier_points1[valid_indices]
    valid_points2 = inlier_points2[valid_indices]
    valid_line_numbers = [inlier_lines[i] for i in valid_indices]
    
    print(f"Final reconstruction has {len(valid_indices)} valid 3D points")
    X_initial = X_best[valid_indices]


    initial_error = calculate_mean_reprojection_error(
        X_initial,
        K,
        np.eye(3), np.zeros(3),  # First camera is at origin
        R_best, C_best,
        valid_points1,
        valid_points2
    )

    print(f"Mean reprojection error before optimization: {initial_error:.4f} pixels")

    X_refined = NonLinearTriangulation(
    K,
    np.eye(3), np.zeros(3),  # First camera is at origin
    R_best, C_best,
    valid_points1,
    valid_points2,
    X_best[valid_indices])

    final_error = calculate_mean_reprojection_error(
            X_refined,
            K,
            np.eye(3), np.zeros(3),
            R_best, C_best,
            valid_points1,
            valid_points2
        )
    print(f"Mean reprojection error after optimization: {final_error:.4f} pixels")

    # VisualizeReconstruction(X_best[valid_indices], R_best, C_best) 
    # VisualizeReconstructionComparison(X_initial, X_refined, R_best, C_best)
    # VisualizeXZPlaneViewInitial(X_initial, R_best, C_best)
    # VisualizeXZPlaneView(X_initial, X_refined, R_best, C_best) 

    VisualizeImagePoints(
    valid_points1, valid_points2,  # Original 2D points
    K,                            # Camera calibration
    np.eye(3), np.zeros(3),      # First camera pose
    R_best, C_best,              # Second camera pose
    X_initial,                    # 3D points from linear triangulation
    X_refined,                    # 3D points from non-linear optimization
    image1_path,                # Path to first image
    image2_path                 # Path to second image
)



if __name__ == "__main__":
    main()
