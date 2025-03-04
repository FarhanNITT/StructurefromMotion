import numpy as np
from scipy.optimize import least_squares
import cv2
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.colors as mcolors
from scipy.spatial.transform import Rotation 
#from calib import BundleAdjustment
from BundleAdjustment import BundleAdjustment, BuildVisibilityMatrix


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


def GetInlierRANSANC(points1, points2, line_numbers, num_iterations=1000, threshold=0.01, seed=42):
    np.random.seed(seed)
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
        #print(f'nonlin triangular error {result.cost}')
        
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
        
        # Set specific axis limits as requested
        plt.xlim(-15, 15)     # X axis from -15 to 15
        plt.ylim(-5, 25)       # Z axis from 0 to 25
        
        # No longer using equal aspect ratio to enforce the specific ranges
        # plt.axis('equal')
        
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


def VisualizeXZPlaneViewComplete(Xset_list, Rset, Cset, image_paths=None):
    """
    Visualize the XZ plane view of the complete 3D reconstruction with multiple cameras.
    
    Args:
        Xset_list: List of arrays containing 3D points for each pair (1,2), (1,3), etc.
        Rset: List of rotation matrices for cameras 2, 3, 4, 5
        Cset: List of camera center positions for cameras 2, 3, 4, 5
        image_paths: Optional list of image file names for labeling
    """

    
    # Create the figure
    plt.figure(figsize=(4.5, 6))
    
    # Define colors for different point sets
    colors = list(mcolors.TABLEAU_COLORS.values())
    
    # Plot the 3D points from each pair with different colors
    for i, X_points in enumerate(Xset_list):
        if X_points is not None and len(X_points) > 0:
            plt.scatter(X_points[:, 0], X_points[:, 2], 
                      c=colors[i % len(colors)], marker='.', s=10, alpha=0.6,
                      label=f'Points from pair (1,{i+2})')
    
    # Plot camera 1 at the origin
    plt.scatter(0, 0, c='black', marker='o', s=150, label='Camera 1 (Reference)')
    
    # Draw camera 1 orientation
    plt.arrow(0, 0, 0.5, 0, head_width=0.1, head_length=0.1, fc='black', ec='black', alpha=0.7)
    plt.arrow(0, 0, 0, 0.5, head_width=0.1, head_length=0.1, fc='black', ec='black', alpha=0.7)
    
    # Plot cameras 2-5 with orientation vectors
    camera_colors = ['red', 'green', 'blue', 'purple']
    
    for i, (R, C) in enumerate(zip(Rset, Cset)):
        # Flatten camera center to get coordinates
        C_pos = C.flatten()
        
        # Label for the camera
        camera_label = f'Camera {i+2}'
        if image_paths and (i+1) < len(image_paths):
            camera_label = f'Camera {i+2} ({image_paths[i+1].split("/")[-1]})'
        
        # Plot the camera
        plt.scatter(C_pos[0], C_pos[2], c=camera_colors[i % len(camera_colors)], 
                   marker='o', s=150, label=camera_label)
        
        # Draw x-axis orientation
        plt.arrow(C_pos[0], C_pos[2], 
                 R[0, 0]*0.5, R[2, 0]*0.5, 
                 head_width=0.1, head_length=0.1, 
                 fc=camera_colors[i % len(camera_colors)], 
                 ec=camera_colors[i % len(camera_colors)], alpha=0.7)
        
        # Draw z-axis orientation (principal axis of the camera)
        plt.arrow(C_pos[0], C_pos[2], 
                 R[0, 2]*0.5, R[2, 2]*0.5, 
                 head_width=0.1, head_length=0.1, 
                 fc=camera_colors[i % len(camera_colors)], 
                 ec=camera_colors[i % len(camera_colors)], alpha=0.7)
        
        # Add text label next to the camera
        plt.text(C_pos[0]+0.1, C_pos[2]+0.1, f'C{i+2}', fontsize=12, 
                color=camera_colors[i % len(camera_colors)])
    
    # Set plot properties
    plt.xlabel('X Axis', fontsize=14)
    plt.ylabel('Z Axis', fontsize=14)
    plt.title('Complete 3D Reconstruction - XZ Plane View', fontsize=16)
    plt.grid(True, alpha=0.3)
    
    # Add a legend with smaller markers for better visibility
    plt.legend(loc='upper right', markerscale=2)
    
    # Determine appropriate axis limits based on both cameras and points
    all_points = np.vstack([X for X in Xset_list if X is not None and len(X) > 0])
    all_cameras = np.vstack([np.zeros(3)] + [C.flatten() for C in Cset])
    
    # Calculate min/max for X and Z coordinates
    min_x = min(np.min(all_points[:, 0]), np.min(all_cameras[:, 0]))
    max_x = max(np.max(all_points[:, 0]), np.max(all_cameras[:, 0]))
    min_z = min(np.min(all_points[:, 2]), np.min(all_cameras[:, 2]))
    max_z = max(np.max(all_points[:, 2]), np.max(all_cameras[:, 2]))
    
    # Add some padding
    padding_x = (max_x - min_x) * 0.1
    padding_z = (max_z - min_z) * 0.1
    
    plt.xlim(min_x - padding_x, max_x + padding_x)
    plt.ylim(min_z - padding_z, max_z + padding_z)
    
    # You can uncomment below to use fixed limits as in your original function
    plt.xlim(-7.5, 10)
    plt.ylim(-5, 20)
    
    plt.tight_layout()
    plt.show()


def VisualizeFinalReconstruction(X_points, Rset, Cset, image_paths=None):
    """
    Visualize the XZ plane view of the complete 3D reconstruction with multiple cameras.
    
    Args:
        X_points: Array of shape (N, 3) containing all 3D points from the complete reconstruction
        Rset: List of rotation matrices for cameras 2, 3, 4, 5
        Cset: List of camera center positions for cameras 2, 3, 4, 5
        image_paths: Optional list of image file names for labeling
    """
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
    
    # Create the figure
    plt.figure(figsize=(4.5, 6))
    
    # Plot all 3D points
    point_colors = ['red', 'green', 'blue', 'orange']

    #X_points = list(X_points)
    
    X_cam2 = X_points[0]
    X_cam2 = np.vstack([X_cam2, X_points[4]])
    #X_cam2 = np.array(X_cam2).reshape(-1, 3)

    plt.scatter(X_cam2[:, 0], X_cam2[:, 2], 
            c='red', marker='.', s=10, alpha=0.6,
            label='3D Points')
    
    X_cam3 = X_points[1]
    X_cam3 = np.vstack([X_cam3, X_points[5]])
    #X_cam3 = np.array(X_cam3).reshape(-1, 3)

    plt.scatter(X_cam3[:, 0], X_cam3[:, 2], 
            c='green', marker='.', s=10, alpha=0.6,
            label='3D Points')
    
    X_cam4 = X_points[2]
    X_cam4 = np.vstack([X_cam4, X_points[6]])
    X_cam4 = np.vstack([X_cam4, X_points[8]])
    #X_cam4 = np.array(X_cam4).reshape(-1, 3)

    plt.scatter(X_cam4[:, 0], X_cam4[:, 2], 
            c='blue', marker='.', s=10, alpha=0.6,
            label='3D Points')
    
    X_cam5 = X_points[3]
    X_cam5 = np.vstack([X_cam5, X_points[7]])
    X_cam5 = np.vstack([X_cam5, X_points[9]])
    X_cam5 = np.vstack([X_cam5, X_points[10]])
    #X_cam5 = np.array(X_cam5).reshape(-1, 3)

    plt.scatter(X_cam5[:, 0], X_cam5[:, 2], 
            c='yellow', marker='.', s=10, alpha=0.6,
            label='3D Points')
    

    
    # Plot camera 1 at the origin
    plt.scatter(0, 0, c='black', marker='^', s=150, label='Camera 1 (Reference)')
    
    # Draw camera 1 orientation
    plt.arrow(0, 0, 0.5, 0, head_width=0.1, head_length=0.1, fc='black', ec='black', alpha=0.7)
    plt.arrow(0, 0, 0, 0.5, head_width=0.1, head_length=0.1, fc='black', ec='black', alpha=0.7)
    
    # Plot cameras 2-5 with orientation vectors
    camera_colors = ['red', 'green', 'blue', 'orange']
    
    for i, (R, C) in enumerate(zip(Rset, Cset)):
        # Flatten camera center to get coordinates
        C_pos = C.flatten()
        
        # Label for the camera
        camera_label = f'Camera {i+2}'
        if image_paths and (i+1) < len(image_paths):
            camera_label = f'Camera {i+2} ({image_paths[i+1].split("/")[-1]})'
        
        # Plot the camera
        plt.scatter(C_pos[0], C_pos[2], c=camera_colors[i % len(camera_colors)], 
                   marker='^', s=150, label=camera_label)
        
        # Draw x-axis orientation
        plt.arrow(C_pos[0], C_pos[2], 
                 R[0, 0]*0.5, R[2, 0]*0.5, 
                 head_width=0.1, head_length=0.1, 
                 fc=camera_colors[i % len(camera_colors)], 
                 ec=camera_colors[i % len(camera_colors)], alpha=0.7)
        
        # Draw z-axis orientation (principal axis of the camera)
        plt.arrow(C_pos[0], C_pos[2], 
                 R[0, 2]*0.5, R[2, 2]*0.5, 
                 head_width=0.1, head_length=0.1, 
                 fc=camera_colors[i % len(camera_colors)], 
                 ec=camera_colors[i % len(camera_colors)], alpha=0.7)
        
        # Add text label next to the camera
        plt.text(C_pos[0]+0.1, C_pos[2]+0.1, f'C{i+2}', fontsize=12, 
                color=camera_colors[i % len(camera_colors)])
    
    # Set plot properties
    plt.xlabel('X Axis', fontsize=14)
    plt.ylabel('Z Axis', fontsize=14)
    plt.title('Complete 3D Reconstruction - XZ Plane View', fontsize=16)
    plt.grid(True, alpha=0.3)
    
    # Add a legend with smaller markers for better visibility
    plt.legend(loc='upper right', markerscale=2)
    
    # Determine appropriate axis limits based on both cameras and points
    all_cameras = np.vstack([np.zeros(3)] + [C.flatten() for C in Cset])
    
    # Calculate min/max for X and Z coordinates
    min_x = min(np.min(X_points[:, 0]), np.min(all_cameras[:, 0]))
    max_x = max(np.max(X_points[:, 0]), np.max(all_cameras[:, 0]))
    min_z = min(np.min(X_points[:, 2]), np.min(all_cameras[:, 2]))
    max_z = max(np.max(X_points[:, 2]), np.max(all_cameras[:, 2]))
    
    # Add some padding
    padding_x = (max_x - min_x) * 0.1
    padding_z = (max_z - min_z) * 0.1
    
    plt.xlim(min_x - padding_x, max_x + padding_x)
    plt.ylim(min_z - padding_z, max_z + padding_z)
    
    # Alternatively, you can use fixed limits if preferred
    plt.xlim(-25, 25)
    plt.ylim(-5, 20)
    
    plt.tight_layout()
    plt.show()
    

# Uncomment to run the example
# example_usage()

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

def LinearPnP(K, X, x):
    """
    Linear Perspective-n-Point algorithm with improved numerical stability
    
    Args:
        K: (3,3) Camera calibration matrix
        X: (N,3) 3D points in world coordinates
        x: (N,2) 2D image points
        
    Returns:
        R: (3,3) Rotation matrix
        C: (3,) Camera center
    """
    # Convert 2D points to normalized coordinates
    x_normalized = np.zeros_like(x)
    K_inv = np.linalg.inv(K)
    
    # Normalize 2D points
    for i in range(x.shape[0]):
        p_homogeneous = np.array([x[i,0], x[i,1], 1.0])
        p_normalized = K_inv @ p_homogeneous
        x_normalized[i] = p_normalized[:2]
    
    # Build the A matrix for DLT
    A = np.zeros((2*len(X), 12))
    
    for i in range(len(X)):
        X_i = X[i]  # 3D point
        x_i = x_normalized[i]  # normalized 2D point
        
        X_homo = np.array([X_i[0], X_i[1], X_i[2], 1])
        
        # Fill in the 2Nx12 matrix
        A[2*i] = np.hstack([X_homo, np.zeros(4), -x_i[0] * X_homo])
        A[2*i + 1] = np.hstack([np.zeros(4), X_homo, -x_i[1] * X_homo])
    
    # Solve using SVD
    _, _, Vh = np.linalg.svd(A)
    P = Vh[-1].reshape(3, 4)
    
    # Extract R and t from P
    R = P[:, :3]
    t = P[:, 3]
    
    # Enforce orthonormality on R
    U, S, Vh = np.linalg.svd(R)
    R = U @ Vh
    t = t/S[0]
    
    # Ensure proper rotation matrix (det(R) = 1)
    if np.linalg.det(R) < 0:
        R = -R
        t = -t
    
    # Calculate camera center
    C = -R.T @ t
    
    return R, C

def PnPRANSAC(X, x, K, epsilon_threshold=0.0001, M=2000, N=None,seed=42):
    """
    RANSAC implementation for PnP with normalized error threshold
    Args:
        X: (N,3) 3D points
        x: (N,2) 2D points
        K: (3,3) camera intrinsic matrix
        epsilon_threshold: threshold for normalized reprojection error (default 0.1)
        M: number of RANSAC iterations
        N: number of points to check (if None, uses all points)
    """
    if N is None:
        N = len(X)
    np.random.seed(seed)
    n = 0  # Size of largest inlier set found so far
    best_S = None  # Best inlier set
    best_R = None
    best_C = None
    
    # Pre-normalize 2D points once
    K_inv = np.linalg.inv(K)
    x_normalized = np.zeros_like(x)
    for i in range(x.shape[0]):
        p_homogeneous = np.array([x[i,0], x[i,1], 1.0])
        p_normalized = K_inv @ p_homogeneous
        x_normalized[i] = p_normalized[:2]
    
    for i in range(M):
        # Choose 6 correspondences randomly
        sample_indices = np.random.choice(len(X), 6, replace=False)
        X_sample = X[sample_indices]
        x_sample = x[sample_indices]
        
        try:
            # Compute pose using LinearPnP
            R, C = LinearPnP(K, X_sample, x_sample)
            
            # Construct projection matrix P (in normalized coordinates)
            t = -R @ C
            P = np.hstack((R, t.reshape(3,1)))  # Note: not using K here
            
            # Initialize inlier set
            S = set()
            
            # Check all N points using normalized coordinates
            for j in range(N):
                # Project 3D point
                X_homogeneous = np.append(X[j], 1)
                x_proj_homogeneous = P @ X_homogeneous
                
                # Convert to inhomogeneous coordinates
                x_proj = x_proj_homogeneous[:2] / x_proj_homogeneous[2]
                
                # Calculate error in normalized coordinates
                error = np.sum((x_normalized[j] - x_proj)**2)
                
                # Check if point is an inlier using normalized threshold
                if error < epsilon_threshold:
                    S.add(j)
            
            # Update best solution if we found more inliers
            if len(S) > n:
                n = len(S)
                best_S = S
                best_R = R
                best_C = C
                
        except np.linalg.LinAlgError:
            continue
    
    if best_S is None:
        raise RuntimeError("RANSAC failed to find a valid solution")
        
    print(f"Found {len(best_S)} inliers out of {N} points")
    
    return best_S, best_R, best_C

# Quaternion and Other Rotation transformations for non lin PnP
def getQuaternion(R2):
    Q = Rotation.from_matrix(R2)
    return Q.as_quat()

def getEuler(R2):
    euler = Rotation.from_matrix(R2)
    return euler.as_rotvec()

def getRotation(Q, type_ = 'q'):
    if type_ == 'q':
        R = Rotation.from_quat(Q)
        return R.as_matrix()
    elif type_ == 'e':
        R = Rotation.from_rotvec(Q)
        return R.as_matrix()

def get_pnp_correspondences(matches_file, ref_image_id, new_image_id, reference_points, valid_line_numbers):
    """
    Get 2D-3D correspondences for PnP by matching points from a new image with existing 3D points.
    
    Args:
        matches_file: Path to matches file (e.g., matching1.txt for image 1's matches)
        ref_image_id: ID of reference image (1 or 2) used in initial reconstruction
        new_image_id: ID of new image for PnP (e.g., 3)
        reference_points: Points from reference image used in reconstruction
        valid_line_numbers: Line numbers of valid points from initial reconstruction
        
    Returns:
        points_3d: Array of 3D points
        points_2d: Corresponding 2D points in new image
    """
    points_2d = []
    points_ref_2d = []  # Keep track of reference image points
    indices = []
    
    with open(matches_file, 'r') as f:
        lines = f.readlines()
        
        # Find nFeatures
        n_features = 0
        for line in lines:
            line = line.strip()
            if line and 'nFeatures' in line:
                n_features = int(line.split(': ')[1])
                break
        
        # Process each feature line
        current_feature = 0
        line_idx = 1  # Skip nFeatures line
        
        while current_feature < n_features and line_idx < len(lines):
            # Get next non-empty line
            while line_idx < len(lines):
                line = lines[line_idx].strip()
                if line:
                    break
                line_idx += 1
            
            if line_idx >= len(lines):
                break
                
            # Only process if this point was used in initial reconstruction
            if (line_idx + 1) in valid_line_numbers:
                try:
                    values = line.split()
                    if not values:
                        line_idx += 1
                        continue
                        
                    line_data = [float(x) for x in values]
                    n_matches = int(line_data[0])
                    ref_u, ref_v = line_data[4:6]  # These are the coordinates in reference image
                    matches_data = line_data[6:]
                    
                    # Look for match with new image
                    for i in range(0, len(matches_data), 3):
                        if i + 2 >= len(matches_data):
                            break
                            
                        match_image_id = int(matches_data[i])
                        match_u = matches_data[i + 1]
                        match_v = matches_data[i + 2]
                        
                        if match_image_id == new_image_id:
                            points_2d.append([match_u, match_v])
                            points_ref_2d.append([ref_u, ref_v])
                            # Get index in reference_points array
                            idx = valid_line_numbers.index(line_idx + 1)
                            indices.append(idx)
                            break
                            
                except (ValueError, IndexError) as e:
                    print(f"Warning: Error processing line {line_idx + 1}: {e}")
                    
            current_feature += 1
            line_idx += 1
    
    points_2d = np.array(points_2d)
    points_ref_2d = np.array(points_ref_2d)
    # Get corresponding 3D points using saved indices
    points_3d = reference_points[indices]
    
    print(f"Found {len(points_2d)} 2D-3D correspondences for PnP")
    # Optional: print some sample correspondences for verification
    # if len(points_2d) > 0:
    #     print("\nSample correspondences (first 3):")
    #     for i in range(min(3, len(points_2d))):
    #         print(f"Ref Image ({points_ref_2d[i]}) → 3D Point ({points_3d[i]}) → New Image ({points_2d[i]})")
    
    return points_3d, points_2d

def project_3d_to_2d(points_3d, K, R, C):
    # Convert camera center to translation vector
    t = -R @ C.reshape(3, 1)
    #t = C.reshape(3, 1)

    # Use cv2.projectPoints to project the 3D points
    projected_points, _ = cv2.projectPoints(
        points_3d, R, t, K, distCoeffs=None
    )
    
    # Flatten the projected points array
    return projected_points.reshape(-1, 2)

def visualize_reprojection(image_path, detected_points, reprojected_points):
    # Load and display the image
    img = cv2.imread(image_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    plt.figure(figsize=(10, 8))
    plt.imshow(img)
    
    # Plot detected points (green)
    plt.scatter(detected_points[:, 0], detected_points[:, 1], 
                c='lime', marker='o', label='Detected Points')
    
    # Plot reprojected points (red)
    plt.scatter(reprojected_points[:, 0], reprojected_points[:, 1], 
                c='red', marker='x', label='Reprojected Points')
    
    plt.legend()
    plt.title("Reprojection Visualization")
    plt.axis("off")
    plt.show()

def NonlinearPnP(K, R_init, C_init, points_3d, points_2d):
    """
    Refine camera pose using non-linear optimization to minimize reprojection error 

    Args:           
        K: Camera calibration matrix (3,3)
        R_init, C_init: Initial camera pose
        points_3d: 3D points
        points_2d: 2D points
    
    Returns:
        R_new, C_new: Refined camera pose
    """
    # Convert rotation matrix to Rodrigues vector
    r_vec, _ = cv2.Rodrigues(R_init)
    r_vec = r_vec.flatten()
    
    # Initial translation vector (negative of R*C)
    t_vec = -R_init @ C_init
    t_vec = t_vec.flatten()  # Ensure t_vec is flattened
    
    # Initial parameters
    params = np.concatenate([r_vec, t_vec])
    
    # Define the objective function
    def objective(params):
        # Extract rotation and translation parameters
        r = params[:3]
        t = params[3:].reshape(3, 1)
        
        # Convert rotation vector back to matrix
        R, _ = cv2.Rodrigues(r)
        
        # Project 3D points to 2D
        projected_points = []
        for point_3d in points_3d:
            # Ensure point_3d is properly shaped
            point_3d = point_3d.reshape(3, 1) if point_3d.ndim == 1 else point_3d
            
            # Convert to camera coordinates
            point_cam = R @ point_3d + t
            
            # Project to image plane
            point_img = K @ point_cam
            point_img = point_img / point_img[2]
            
            # Only append the x,y coordinates (first 2 elements)
            projected_points.append(point_img[:2].flatten())
        
        projected_points = np.array(projected_points)
        
        # Calculate reprojection error
        error = points_2d - projected_points
        
        return error.flatten()
    
    # Use least_squares to minimize reprojection error
    result = least_squares(
        objective,
        params,
        method='trf',  # Trust Region Reflective algorithm
        loss='huber',  # Robust loss function to handle outliers
        max_nfev=1000,  # Maximum number of function evaluations
        verbose=0
    )
    
    # Extract refined parameters
    r_refined = result.x[:3]
    t_refined = result.x[3:]
    
    # Convert rotation vector to matrix
    R_refined, _ = cv2.Rodrigues(r_refined)
    
    # Calculate camera center (C = -R^T * t)
    C_refined = -R_refined.T @ t_refined.reshape(3, 1)
    
    # Calculate and print mean reprojection error
    errors = result.fun.reshape(-1, 2)
    mean_error = np.mean(np.sqrt(np.sum(errors**2, axis=1)))
    print(f"Mean reprojection error after NonlinearPnP: {mean_error:.3f} pixels")
    
    return R_refined, C_refined.flatten() 
def flatten_list(nested_list):
    return [item for sublist in nested_list for item in sublist]

# def BuildVisibilityMatrix(K,Rset,Cset,Xset):

#     all_points = flatten_list(Xset)

#     all_points_3d = np.asarray(all_points, dtype=np.float32)
    
#     # OpenCV's projectPoints expects 3D points with shape (n, 1, 3) or (n, 3)
#     # Check and reshape if needed
#     if all_points_3d.ndim == 2 and all_points_3d.shape[1] == 3:
#         # Already in (n, 3) format, which is fine
#         pass
#     else:
#         # Try to reshape to correct format
#         try:
#             all_points_3d = all_points_3d.reshape(-1, 3)
#         except:
#             raise ValueError("points_3d must be convertible to shape (n, 3)")

#     visibility_matrix = np.zeros((len(Rset),len(all_points_3d)))

#     for i in range(len(Rset)):
#         R = Rset[i]
#         C = Cset[i]

#         points_2d = project_3d_to_2d(all_points_3d, K, R, C)

#         # check if points are within image bounds
#         # row = np.zeros((1,len(Xset)))
#         row = []
#         n_1 = 0
#         n_0 = 0
#         # each image is (600, 800, 3)
#         for j in range(len(points_2d)):
#             x = points_2d[j][0]
#             y = points_2d[j][1]

#             if x >= 0 and x < 800 and y >= 0 and y < 600:
#                 row.append(1)
#                 n_1 += 1
#             else:
#                 row.append(0)
#                 n_0 += 1
#         print(f"Image {i+2} has {n_1} points within bounds and {n_0} points outside bounds")
#         visibility_matrix[i] = row
    
#     return visibility_matrix

# Add this function to filter 3D points and their corresponding 2D projections
def filter_points_by_range(all_points, all_points_2d, x_range=(-20, 20), z_range=(-5, 25)):
    """
    Filter 3D points to only include those within specified ranges for x and z coordinates.
    Also removes the corresponding 2D points from all_points_2d.
    
    Args:
        all_points: List of 3D points
        all_points_2d: List of corresponding 2D points across multiple views
        x_range: Tuple of (min_x, max_x)
        z_range: Tuple of (min_z, max_z)
        
    Returns:
        filtered_points: Filtered 3D points
        filtered_points_2d: Filtered 2D points
    """
    # Convert to numpy array if not already
    points_array = np.array(all_points)
    
    # Create a mask for points within the range
    x_mask = (points_array[:, 0] >= x_range[0]) & (points_array[:, 0] <= x_range[1])
    z_mask = (points_array[:, 2] >= z_range[0]) & (points_array[:, 2] <= z_range[1])
    valid_mask = x_mask & z_mask
    
    # Filter 3D points
    filtered_points = points_array[valid_mask]
    
    # Filter 2D points in each view
    filtered_points_2d = []
    for view_points in all_points_2d:
        if view_points is not None:
            view_points_array = np.array(view_points)
            filtered_view_points = view_points_array[valid_mask[:len(view_points_array)]] if len(view_points_array) > 0 else np.array([])
            filtered_points_2d.append(filtered_view_points)
        else:
            filtered_points_2d.append(None)
    
    # Print statistics for debugging
    print(f"Total points: {len(points_array)}")
    print(f"Points within range: {len(filtered_points)}")
    print(f"Removed {len(points_array) - len(filtered_points)} outlier points")
    
    return filtered_points, filtered_points_2d
        

def main():
    # Example usage with your matches.txt file
    matches_file = 'matching1.txt'
    image_id1 = 1  # Replace with your first image ID
    image_id2 = 2 # Replace with your second image ID
    image1_path = r'1.png'
    image2_path = r'2.png'
    image3_path = r'3.png'
    
    Rset = []
    Cset = []
    Xset = []

    # Parse matching points between image 1 and 2
    points1, points2, line_numbers = read_matches_file(matches_file, image_id1, image_id2)
    
    if len(points1) < 8:
        print(f"Not enough matches found between images {image_id1} and {image_id2}")
        print(f"Found {len(points1)} matches, need at least 8")
        return
    
    # Run RANSAC to find inliers and estimate F
    best_F, initial_inliers, inlier_lines = GetInlierRANSANC(points1, points2, line_numbers)
    
    # Calculate error using inliers
    if len(initial_inliers) >= 8:
        inlier_points1 = points1[initial_inliers]
        inlier_points2 = points2[initial_inliers]
        error = calculate_epipolar_error(best_F, inlier_points1, inlier_points2)
    else:
        print("Failed to find enough inliers using RANSAC")

    K = np.loadtxt('calibration.txt')
    E = EssentialMatrixFromFundamentalMatrix(best_F,K)
    

    Rs,Cs = ExtractCameraPose(E)

    # Disambiguate camera pose using cheirality check
    R1, C1, X1, valid_indices = DisambiguateCameraPose(Rs, Cs, K, inlier_points1, inlier_points2)
    
    # Extract valid points
    valid_points1 = inlier_points1[valid_indices]
    valid_points2 = inlier_points2[valid_indices]
    valid_line_numbers = [inlier_lines[i] for i in valid_indices]
    
    X_initial = X1[valid_indices]


    initial_error = calculate_mean_reprojection_error(
        X_initial,
        K,
        np.eye(3), np.zeros(3),  # First camera is at origin
        R1, C1,
        valid_points1,
        valid_points2
    )


    X1_refined = NonLinearTriangulation(
    K,
    np.eye(3), np.zeros(3),  # First camera is at origin
    R1, C1,
    valid_points1,
    valid_points2,
    X_initial 
)

    final_error = calculate_mean_reprojection_error(
            X1_refined,
            K,
            np.eye(3), np.zeros(3),
            R1, C1,
            valid_points1,
            valid_points2
        )

    Rset.append(R1)
    Cset.append(C1)
    Xset.append(X1_refined)

#     VisualizeImagePoints(
#     valid_points1, valid_points2,  # Original 2D points
#     K,                            # Camera calibration
#     np.eye(3), np.zeros(3),      # First camera pose
#     R1, C1,              # Second camera pose
#     X_initial,                    # 3D points from linear triangulation
#     X1_refined,                    # 3D points from non-linear optimization
#     image1_path,                # Path to first image
#     image2_path                 # Path to second image
# )

    VisualizeXZPlaneViewInitial(X1_refined, R1, C1)

    R_dict = {}
    C_dict = {}

    all_points_2d = [None,None,None,None]
    all_points_2d[0] = valid_points2

    for i in range(3, 6):
    
        points_3d, points_2d = get_pnp_correspondences(
        'matching1.txt',  # matches between image 2 and 3
        1,               # reference image ID (image 2)
        i,               # new image ID
        X1_refined,       # refined 3D points
        valid_line_numbers  )


        if len(points_2d) >= 6:  # Minimum points needed for PnP
            #R_, C_ = LinearPnP(K, points_3d, points_2d)

            inliers_pnp,R0,C0 = PnPRANSAC(points_3d, points_2d, K, epsilon_threshold=0.1)

        

        inlier_indices = np.array(list(inliers_pnp))
        # inlier_points = X1_refined[inlier_indices] 
        inlier_points_3d = points_3d[inlier_indices]
        inlier_points_2d = points_2d[inlier_indices]


        # Refine camera pose using non-linear optimization
        R_dict[i], C_dict[i] = NonlinearPnP(K, R0, C0, inlier_points_3d, inlier_points_2d)
        
        reprojected_points_refined = project_3d_to_2d(inlier_points_3d, K, R_dict[i], C_dict[i])

        # Visualize reprojection on an image
        #visualize_reprojection(f'{i}.png', inlier_points_2d, reprojected_points_refined)
        
        pts1, pts2, line_num = read_matches_file(matches_file, image_id1, i)

        # # Get inliners from these matches
        # _,pts1_idx,lines = GetInlierRANSANC(pts1, pts2, line_num,num_iterations=1000, threshold=1)

        # if len(pts1_idx) >= 8:
        #     pts1 = pts1[pts1_idx]
        #     pts2 = pts2[pts1_idx]

        print(len(pts1))
        X0, valid_id = LinearTriangulation(K, np.zeros((3, 1)), np.eye(3), C_dict[i], R_dict[i], pts1, pts2)

        k = i - 2
        all_points_2d[k] = pts2[valid_id]

        print(len(valid_id))
        X0_refined = NonLinearTriangulation(
        K,
        np.eye(3), np.zeros((3,1)),  # First camera is at origin
        R_dict[i], C_dict[i],
        pts1[valid_id],
        pts2[valid_id],
        X0[valid_id])

        print(len(X0_refined))

        Rset.append(R_dict[i])
        Cset.append(C_dict[i])
        Xset.append(X0_refined)

        # print(len(X0_refined)) 
        #VisualizeXZPlaneViewInitial(X0_refined, R_dict[i], C_dict[i]) 
    
    # VisualizeXZPlaneViewComplete(Xset[:2], Rset[:2], Cset[:2])

    print(Rset)

    pts_flat = flatten_list(all_points_2d)
    all_points = flatten_list(Xset)
    #print(all_points_2d.shape) #Not a numpy array so this gives error

    #Removing points outside the range
    #all_points,all_points_2d = filter_points_by_range(all_points, all_points_2d, x_range=(-20, 20), z_range=(-5, 25))

    # Visualise before BA
    VisualizeFinalReconstruction(np.array(all_points), Rset, Cset)
  
    visibility_matrix = BuildVisibilityMatrix(K,Rset,Cset,Xset)
    # print(Rset)
    # print(Cset)
    refined_points, refined_Rset, refined_Cset = BundleAdjustment(K,Rset,Cset,all_points,all_points_2d,visibility_matrix)

    # print("Again")

    # refined_points, refined_Rset, refined_Cset = BundleAdjustment(
    #     K, Rset, Cset, all_points, all_points_2d, visibility_matrix,
    #     method='trf',
    #     max_iterations=1000,
    #     ftol=1e-10,
    #     outlier_threshold=5.0,  # Stricter outlier rejection
    #     regularization_weight=0.005  # Adjust based on your data scale
    # )
    #refined_points1, refined_Rset1, refined_Cset1 = BundleAdjustment(K,refined_Rset,refined_Cset,refined_points,all_points_2d,visibility_matrix)
    print(refined_points.shape)
    print(X1_refined.shape)
    refined_points = np.vstack([refined_points,X1_refined])
    Xset.append(X1_refined)
    
    #VisualizeFinalReconstruction(refined_points, refined_Rset, refined_Cset) 

    # After your bundle adjustment code, where you already have:
    # refined_points = np.vstack([refined_points, X1_refined])

    # Define the camera pairs to process
    camera_pairs = [(2, 3), (2, 4), (2, 5), (3, 4), (3, 5), (4, 5)]

    # For each camera pair
    for cam1_idx, cam2_idx in camera_pairs:
        # Get camera indices in your Rset, Cset (adjusting for 0-based indexing if needed)
        # If your cameras are indexed starting from 1 in your code, but 0-based in arrays:
        c1_idx = cam1_idx   # Adjust if necessary
        c2_idx = cam2_idx   # Adjust if necessary
        
        # Read matching points between the two cameras
        matches_file = f'matching{c1_idx}.txt'  # Update if you have different files for different pairs
        pts1, pts2, line_numbers = read_matches_file(matches_file, cam1_idx, cam2_idx)
        
        # Find inliers if needed (similar to your existing code)
        # You might want to use RANSAC to filter matches
        _, inliers_idx, _ = GetInlierRANSANC(pts1, pts2, line_numbers, threshold=0.001)
        
        if len(inliers_idx) >= 8:  # Enough points for triangulation
            inlier_pts1 = pts1[inliers_idx]
            inlier_pts2 = pts2[inliers_idx]
            
        # Linear triangulation to get initial 3D points
        X_initial, valid_indices = LinearTriangulation(
            K, 
            refined_Cset[c1_idx-2], refined_Rset[c1_idx-2], 
            refined_Cset[c2_idx-2], refined_Rset[c2_idx-2], 
            inlier_pts1, inlier_pts2
        )
        
        # Apply non-linear triangulation to refine the points
        X_refined = NonLinearTriangulation(
            K,
            refined_Rset[c1_idx-2], refined_Cset[c1_idx-2],
            refined_Rset[c2_idx-2], refined_Cset[c2_idx-2],
            inlier_pts1[valid_indices],
            inlier_pts2[valid_indices],
            X_initial[valid_indices]
        )
        
        # Add these new points to refined_points
        refined_points = np.vstack([refined_points, X_refined])
        Xset.append(X_refined)
        
        print(f"Added {len(X_refined)} points from camera pair ({cam1_idx}, {cam2_idx})")

    print(len(Xset))
    VisualizeFinalReconstruction(Xset, refined_Rset, refined_Cset)
    

if __name__ == "__main__":
    main()
